import os
from pathlib import Path

from flask import Flask, flash, render_template, request, redirect
from flask_login import (
    UserMixin,
    LoginManager,
    current_user,
    login_user,
    logout_user,
    login_required,
)
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, memo,user

DATABASE = "flaskmemo.db"
login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, userid):
        self.id = userid


@login_manager.user_loader
def load_user(userid):
    return User(userid)


@login_manager.unauthorized_handler
def unauthorized():
    return redirect("/login")


# アプリ作成
def create_app():
    app = Flask(__name__)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database_path = Path(app.instance_path) / DATABASE

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/logout", methods=["GET"])
    def logout():
        logout_user()
        flash("ログアウトしました。","secondary")
        return redirect("/")

    # ユーザー登録
    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        error_message = ""

        if request.method == "POST":
            userid = request.form.get("userid")
            password = request.form.get("password")
            pass_hash = generate_password_hash(password)

            user_check = db.session.execute(
                text("SELECT userid FROM user WHERE userid = :userid"),
                {"userid": userid},
            ).first()

            if user_check is None:
                db.session.execute(
                    text(
                        "INSERT INTO user "
                        "(userid, password) "
                        "VALUES (:userid, :password)"
                    ),
                    {"userid": userid, "password": pass_hash},
                )
                db.session.commit()
                flash("ユーザー登録に成功しました","success")
                return redirect("/login")

            error_message = "入力されたユーザーIDはすでに利用されています"
            flash(error_message,"danger")
        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error_message = ""
        userid = ""

        if request.method == "POST":
            userid = request.form.get("userid")
            password = request.form.get("password")

            # ログインチェック
            pass_hash = db.session.execute(
                text("SELECT password FROM user WHERE userid = :userid"),
                {"userid": userid},
            ).scalar_one_or_none()

            if pass_hash is not None and check_password_hash(pass_hash, password):
                user = User(userid)
                login_user(user)
                flash("ログインに成功しました", "success")
                return redirect("/")

            error_message = "入力されたIDもしくはパスワードは誤っています"
            flash(error_message, "danger")
        return render_template("login.html", userid=userid)
    @app.route("/")
    @login_required
    def top():
        userid = current_user.id
        # ログイン中のunum取得
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"),
            {"userid": userid}
        ).scalar_one_or_none()

        keyword = request.args.get("keyword", "")

        memo_list = (
            db.session.execute(
                text(
                    "SELECT id, title, body, created_at, updated_at  FROM memo "
                    "WHERE createduser = :userid "
                    "AND (title LIKE :keyword OR body LIKE :keyword)"
                ),
                {"userid": unum, "keyword": f"%{keyword}%"},
            )
            .mappings()
            .all()
        )

        return render_template("index.html", memo_list=memo_list)

    @app.route("/regist", methods=["GET", "POST"])
    @login_required
    def regist():
        # 現在ログインしているユーザーIDとunumを取得
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"),
            {"userid": userid}
        ).scalar_one_or_none()

        if request.method == "POST":
            title = request.form.get("title")
            body = request.form.get("body")

            new_memo = memo(
                title=title,
                body=body,
                createduser=unum
            )

            db.session.add(new_memo)
            db.session.commit()
            flash("メモの登録に成功しました。","success")
            return redirect("/")

        return render_template("regist.html")

    @app.route("/<int:id>/edit", methods=["GET", "POST"])
    @login_required
    def edit(id):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"),
            {"userid": userid}
        ).scalar_one_or_none()

        post = memo.query.filter_by(id=id, createduser=unum).first()

        if post is None:
            return redirect("/")

        if request.method == "POST":
            post.title = request.form.get("title")
            post.body = request.form.get("body")

            db.session.commit()
            flash("メモの編集に成功しました。", "primary")
            return redirect("/")

        return render_template("edit.html", post=post)  

    @app.route("/<int:id>/delete", methods=["GET", "POST"])
    @login_required
    def delete(id):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        post = memo.query.filter_by(id=id, createduser=unum).first()

        if post is None:
            return redirect("/")

        if request.method == "POST":
            db.session.delete(post)
            db.session.commit()
            flash("メモの削除に成功しました。", "secondary")
            return redirect("/")

        return render_template("delete.html", post=post)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
