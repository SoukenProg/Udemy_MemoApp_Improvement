import os
from pathlib import Path

from flask import Flask, flash, render_template, request, redirect, url_for
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

from models import db, memo, user, category

DATABASE = "flaskmemo.db"
# カテゴリー機能の初期値と表示優先度
DEFAULT_CATEGORIES = [
    ("未分類", 0),
    ("学習", 1),
    ("仕事", 1),
    ("アイデア", 1),
    ("その他", 2),
]
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
        flash("ログアウトしました。", "secondary")
        return redirect(url_for("top"))

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

                # 登録したユーザーのunumを取得
                new_unum = db.session.execute(
                    text("SELECT unum FROM user WHERE userid = :userid"),
                    {"userid": userid},
                ).scalar_one()

                # 初期カテゴリを登録
                for category_name, priority in DEFAULT_CATEGORIES:
                    db.session.execute(
                        text(
                            "INSERT INTO category (name, createduser,priority) "
                            "VALUES (:name, :createduser, :priority)"
                        ),
                        {
                            "name": category_name,
                            "createduser": new_unum,
                            "priority": priority,
                        },
                    )
                db.session.commit()
                flash("ユーザー登録に成功しました", "success")
                return redirect("/login")

            error_message = "入力されたユーザーIDはすでに利用されています"
            flash(error_message, "danger")
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
                return redirect(url_for("top"))

            error_message = "入力されたIDもしくはパスワードは誤っています"
            flash(error_message, "danger")
        return render_template("login.html", userid=userid)

    @app.route("/")
    @login_required
    def top():
        userid = current_user.id
        # ログイン中のunum取得
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        keyword = request.args.get("keyword", "")
        category_id = request.args.get("category_id", type=int)

        # ログインユーザーのカテゴリ一覧
        category_list = (
            category.query.filter_by(createduser=unum)
            .order_by(category.priority, category.id)
            .all()
        )
        
        # カテゴリが指定されている場合だけ、
        # 現在のログインユーザーのカテゴリか確認する
        if category_id is not None:
            selected_category = category.query.filter_by(
                id=category_id, createduser=unum
            ).first()

            if selected_category is None:
                flash("選択されたカテゴリは使用できません。", "danger")
                return redirect(url_for("top"))
        # 実行するSQLとパラメータ
        sql = (
            "SELECT "
            "memo.id, "
            "memo.title, "
            "memo.body, "
            "memo.created_at, "
            "memo.updated_at, "
            "memo.category_id, "
            "category.name AS category_name "
            "FROM memo "
            "LEFT JOIN category ON memo.category_id = category.id "
            "WHERE memo.createduser = :userid "
            "AND (memo.title LIKE :keyword OR memo.body LIKE :keyword) "
        )
        params = {"userid": unum, "keyword": f"%{keyword}%"}
        # カテゴリが選択されているとき
        if category_id is not None:
            sql += "AND memo.category_id = :category_id "
            params["category_id"] = category_id

        # 更新日時の新しい順に表示
        sql += "ORDER BY memo.updated_at DESC "
        memo_list = db.session.execute(text(sql), params=params).mappings().all()

        return render_template(
            "index.html",
            memo_list=memo_list,
            category_list=category_list,
            keyword=keyword,
            selected_category_id=category_id,
        )

    @app.route("/category/add", methods=["GET", "POST"])
    @login_required
    def add_category():
        # 現在ログインしているユーザーIDとunumを取得
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()
        # 現在ログインしているユーザーのカテゴリを取得
        category_list = (
            category.query.filter_by(createduser=unum).order_by(category.priority).all()
        )

        if request.method == "POST":
            new_category = request.form.get("category", "").strip()
            if not new_category:
                flash("追加するカテゴリを入力してください。", "danger")
                return render_template("add_category.html", category_list=category_list)
            new_category = category(name=new_category, createduser=unum)

            db.session.add(new_category)
            db.session.commit()
            flash("カテゴリの登録に成功しました。", "success")
            return redirect(url_for("view_category"))

        return render_template("add_category.html", category_list=category_list)

    @app.route("/regist", methods=["GET", "POST"])
    @login_required
    def regist():
        # 現在ログインしているユーザーIDとunumを取得
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()
        # 現在ログインしているユーザーのカテゴリを取得
        category_list = (
            category.query.filter_by(createduser=unum).order_by(category.priority).all()
        )

        if request.method == "POST":
            # 内容があるかチェック
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            category_id = request.form.get("category_id")

            if not title:
                flash("タイトルを入力してください。", "danger")
                return render_template("regist.html", category_list=category_list)

            if not body:
                flash("本文を入力してください。", "danger")
                return render_template("regist.html", category_list=category_list)

            if category_id is None:
                flash("カテゴリを選択してください。", "danger")
                return render_template("regist.html", category_list=category_list)

            new_memo = memo(
                title=title, body=body, createduser=unum, category_id=category_id
            )

            db.session.add(new_memo)
            db.session.commit()
            flash("メモの登録に成功しました。", "success")
            return redirect(url_for("top"))

        return render_template("regist.html", category_list=category_list)

    @app.route("/<int:id>/edit", methods=["GET", "POST"])
    @login_required
    def edit(id):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        post = memo.query.filter_by(id=id, createduser=unum).first()

        if post is None:
            flash("指定されたメモは存在しません。", "danger")
            return redirect(url_for("top"))

        category_list = (
            category.query.filter_by(createduser=unum)
            .order_by(category.priority, category.id)
            .all()
        )
        # 選択中のカテゴリー
        selected_category = post.category_id
        if request.method == "POST":
            # 内容があるかチェック
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            category_id = request.form.get("category_id")

            if not title:
                flash("タイトルを入力してください。", "danger")
                return render_template(
                    "edit.html", post=post, category_list=category_list
                )

            if not body:
                flash("本文を入力してください。", "danger")
                return render_template(
                    "edit.html", post=post, category_list=category_list
                )

            if category_id is None:
                flash("カテゴリを選択してください。", "danger")
                return render_template(
                    "edit.html", post=post, category_list=category_list
                )

            # POSTで送信されたカテゴリが、
            # 現在のログインユーザーのカテゴリか確認する
            selected_category = category.query.filter_by(
                id=category_id, createduser=unum
            ).first()

            if selected_category is None:
                flash("選択されたカテゴリは使用できません。", "danger")
                return render_template(
                    "edit.html", post=post, category_list=category_list
                )

            post.title = title
            post.body = body
            post.category_id = selected_category.id

            db.session.commit()

            flash("メモの編集に成功しました。", "primary")
            return redirect(url_for("top"))

        return render_template(
            "edit.html",
            post=post,
            category_list=category_list,
            selected_category=selected_category,
        )

    @app.route("/category", methods=["GET", "POST"])
    @login_required
    def view_category():
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        category_list = (
            category.query.filter_by(createduser=unum).order_by(category.priority).all()
        )

        if category_list is None:
            return redirect(url_for("top"))

        return render_template("view_category.html", category_list=category_list)

    @app.route("/category/<int:cid>/edit", methods=["GET", "POST"])
    @login_required
    def edit_category(cid):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        edit_target = category.query.filter_by(id=cid, createduser=unum).first()

        if edit_target is None:
            flash("編集対象のカテゴリが存在しません。", "danger")
            return redirect(url_for("view_category"))

        # 「未分類」「その他」カテゴリを取得
        uncategorized = category.query.filter_by(
            name="未分類", createduser=unum
        ).first()
        other_category = category.query.filter_by(
            name="その他", createduser=unum
        ).first()

        if edit_target.id in [uncategorized.id, other_category.id]:
            flash("このカテゴリは編集できません。", "danger")
            return render_template("edit_category.html", category=edit_target)

        if request.method == "POST":
            edit_target.name = request.form.get("category")

            db.session.commit()
            flash("カテゴリの編集に成功しました。", "primary")
            return redirect("/category")

        return render_template("edit_category.html", category=edit_target)

    @app.route("/<int:id>/delete", methods=["GET", "POST"])
    @login_required
    def delete(id):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        post = memo.query.filter_by(id=id, createduser=unum).first()

        if post is None:
            return redirect(url_for("top"))

        if request.method == "POST":
            db.session.delete(post)
            db.session.commit()
            flash("メモの削除に成功しました。", "secondary")
            return redirect(url_for("top"))

        return render_template("delete.html", post=post)

    @app.route("/category/<int:cid>/delete", methods=["GET", "POST"])
    @login_required
    def delete_category(cid):
        userid = current_user.id
        unum = db.session.execute(
            text("SELECT unum FROM user WHERE userid = :userid"), {"userid": userid}
        ).scalar_one_or_none()

        # 削除対象カテゴリ
        delete_target = category.query.filter_by(id=cid, createduser=unum).first()

        # 対象が存在しない、または他ユーザーのカテゴリの場合
        if delete_target is None:
            flash("指定されたカテゴリは存在しません。", "danger")
            return redirect(url_for("view_category"))

        # 「未分類」「その他」カテゴリを取得
        uncategorized = category.query.filter_by(
            name="未分類", createduser=unum
        ).first()
        other_category = category.query.filter_by(
            name="その他", createduser=unum
        ).first()

        if delete_target.id in [uncategorized.id, other_category.id]:
            flash("このカテゴリは削除できません。", "danger")
            return redirect(url_for("view_category"))

        if request.method == "POST":
            # 削除対象カテゴリを使用しているメモを「未分類」へ移動
            memo.query.filter_by(category_id=delete_target.id, createduser=unum).update(
                {"category_id": uncategorized.id}, synchronize_session=False
            )

            # カテゴリを削除
            db.session.delete(delete_target)

            # メモの更新とカテゴリ削除をまとめて確定
            db.session.commit()

            flash(
                f"カテゴリ「{delete_target.name}」を削除しました。"
                "関連するメモのカテゴリを「未分類」へ移動しました。",
                "secondary",
            )
            return redirect(url_for("view_category"))

        return render_template("delete_category.html", category=delete_target)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
