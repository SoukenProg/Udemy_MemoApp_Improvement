import os
from pathlib import Path
import random
from datetime import datetime, timedelta

import click

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
SORT_PRIORITY = [
    "更新日時が新しい順",
    "更新日時が古い順",
    "作成日時が新しい順",
    "作成日時が古い順",
]
SORT_PRIORITY_SQL = [
    "ORDER BY memo.updated_at DESC ",
    "ORDER BY memo.updated_at ASC ",
    "ORDER BY memo.created_at DESC ",
    "ORDER BY memo.created_at ASC ",
]
# 1ページ当たりのメモ数
MEMOS_PER_PAGE = 10
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
        sort_id = request.args.get("sort_id", default=0, type=int)
        page = request.args.get("page",default=1,type=int)

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

        # ソートIDの不正チェック
        if sort_id < 0 or sort_id >= len(SORT_PRIORITY):
            flash("不正なソートIDです。", "danger")
            return redirect(url_for("top"))

        # ページ番号
        page = request.args.get("page", default=1, type=int)

        if page < 1:
            page = 1

        # 件数取得用SQL
        count_sql = (
            "SELECT COUNT(*) "
            "FROM memo "
            "WHERE memo.createduser = :userid "
            "AND (memo.title LIKE :keyword OR memo.body LIKE :keyword) "
        )

        count_params = {
            "userid": unum,
            "keyword": f"%{keyword}%"
        }

        if category_id is not None:
            count_sql += "AND memo.category_id = :category_id "
            count_params["category_id"] = category_id

        total_count = db.session.execute(
            text(count_sql),
            count_params
        ).scalar_one()

        total_pages = (total_count + MEMOS_PER_PAGE - 1) // MEMOS_PER_PAGE

        if total_pages > 0 and page > total_pages:
            return redirect(
                url_for(
                    "top",
                    page=total_pages,
                    keyword=keyword,
                    category_id=category_id,
                    sort_id=sort_id,
                )
            )
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

        # sort_idの指示通りにソート
        sql += SORT_PRIORITY_SQL[sort_id]
        sql += "limit :limit offset :offset"
        params["limit"] = MEMOS_PER_PAGE
        params["offset"] = MEMOS_PER_PAGE * (page - 1)
        memo_list = db.session.execute(text(sql), params=params).mappings().all()

        return render_template(
            "index.html",
            memo_list=memo_list,
            category_list=category_list,
            keyword=keyword,
            selected_category_id=category_id,
            sort_priority=SORT_PRIORITY,
            select_sort_id=sort_id,
            page=page,
            total_pages=total_pages
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
            category_check = category.query.filter_by(
                name=new_category, createduser=unum
            ).first()
            if category_check is None:
                new_category = category(name=new_category, createduser=unum)

                db.session.add(new_category)
                db.session.commit()
                flash("カテゴリの登録に成功しました。", "success")
                return redirect(url_for("view_category"))

            flash("このカテゴリ名はすでに使用されています","danger")
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

            selected_category = category.query.filter_by(
                id=category_id,
                createduser=unum
            ).first()

            if selected_category is None:
                flash("選択されたカテゴリは使用できません。", "danger")
                return render_template(
                    "regist.html",
                    category_list=category_list
                )

            new_memo = memo(
                title=title,
                body=body,
                createduser=unum,
                category_id=selected_category.id
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
            new_name = request.form.get("category", "").strip()
    
            if not new_name:
                flash("カテゴリ名を入力してください。", "danger")
                return render_template(
                    "edit_category.html",
                    category=edit_target
                )
            # 変更先のカテゴリがすでにあるか
            duplicate_category = (
                category.query
                .filter(
                category.createduser == unum,
                category.name == new_name,
                    category.id != edit_target.id
                )
                .first()
            )

            if duplicate_category is not None:
                flash("このカテゴリ名はすでに使用されています。", "danger")
                return render_template(
                    "edit_category.html",
                    category=edit_target
                )

            edit_target.name = new_name

            db.session.commit()

            flash("カテゴリの編集に成功しました。", "primary")
            return redirect(url_for("view_category"))

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

    @app.cli.command("seed-memos")
    @click.option(
        "--userid",
        required=True,
        help="モックメモを登録するユーザーID",
    )
    @click.option(
        "--count",
        default=100,
        type=click.IntRange(min=1),
        show_default=True,
        help="作成するモックメモの件数",
    )
    def seed_memos(userid, count):
        """指定ユーザーにモックメモを登録する。"""

        target_user = user.query.filter_by(userid=userid).first()

        if target_user is None:
            click.echo(f"ユーザーID「{userid}」は存在しません。")
            return

        category_list = (
            category.query
            .filter_by(createduser=target_user.unum)
            .all()
        )

        if not category_list:
            click.echo(
                f"ユーザーID「{userid}」にはカテゴリが登録されていません。"
            )
            return

        sample_titles = [
            "Pythonの学習メモ",
            "Flaskの実装メモ",
            "今日のタスク",
            "アイデアの記録",
            "業務改善案",
            "SQLAlchemyの確認",
            "ポートフォリオ作業",
            "面接準備",
            "買い物リスト",
            "今後の予定",
        ]

        sample_bodies = [
            "これはページネーション確認用のモックデータです。",
            "検索機能とカテゴリ絞り込みの動作を確認します。",
            "並び替え機能をテストするために作成したメモです。",
            "FlaskとSQLAlchemyの実装内容を整理します。",
            "一覧画面の表示件数を確認するためのデータです。",
            "カテゴリごとの表示結果を確認します。",
            "作成日時と更新日時の並び順を確認します。",
            "ページ移動後に検索条件が維持されるか確認します。",
            "モックデータとして自動生成された本文です。",
            "開発中のテスト用途で登録されたメモです。",
        ]

        created_count = 0

        try:
            for index in range(1, count + 1):
                selected_category = random.choice(category_list)

                created_at = datetime.now() - timedelta(
                    days=random.randint(0, 180),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )

                updated_at = created_at + timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                )

                # 更新日時が未来にならないよう調整
                if updated_at > datetime.now():
                    updated_at = datetime.now()

                mock_memo = memo(
                    title=(
                        f"[MOCK] {sample_titles[(index - 1) % len(sample_titles)]} "
                        f"{index:03d}"
                    ),
                    body=(
                        f"{sample_bodies[(index - 1) % len(sample_bodies)]}\n"
                        f"モックデータ番号: {index:03d}"
                    ),
                    createduser=target_user.unum,
                    category_id=selected_category.id,
                    created_at=created_at,
                    updated_at=updated_at,
                )

                db.session.add(mock_memo)
                created_count += 1

            db.session.commit()

        except Exception as error:
            db.session.rollback()
            click.echo(f"モックデータの登録に失敗しました: {error}")
            return

        click.echo(
            f"ユーザーID「{userid}」に"
            f"{created_count}件のモックメモを登録しました。"
        )

    @app.cli.command("delete-mock-memos")
    @click.option(
        "--userid",
        required=True,
        help="モックメモを削除するユーザーID",
    )
    def delete_mock_memos(userid):
        """指定ユーザーのモックメモだけを削除する。"""

        target_user = user.query.filter_by(userid=userid).first()

        if target_user is None:
            click.echo(f"ユーザーID「{userid}」は存在しません。")
            return

        mock_memo_list = (
            memo.query
            .filter(
                memo.createduser == target_user.unum,
                memo.title.like("[MOCK]%"),
            )
            .all()
        )

        if not mock_memo_list:
            click.echo(
                f"ユーザーID「{userid}」に"
                "削除対象のモックメモはありません。"
            )
            return

        delete_count = len(mock_memo_list)

        try:
            for mock_memo in mock_memo_list:
                db.session.delete(mock_memo)

            db.session.commit()

        except Exception as error:
            db.session.rollback()
            click.echo(f"モックデータの削除に失敗しました: {error}")
            return

        click.echo(
            f"ユーザーID「{userid}」の"
            f"モックメモを{delete_count}件削除しました。"
        )
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
