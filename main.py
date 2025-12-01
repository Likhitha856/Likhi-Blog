from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import RegisterForm
from forms import CreatePostForm
from forms import LoginForm
from forms import CommentForm
import os
import smtplib
from dotenv import load_dotenv
load_dotenv()

MY_EMAIL=os.getenv('MY_EMAIL')
PASSWORD=os.getenv('PASSWORD')

basedir = os.path.abspath(os.path.dirname(__file__))


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
ckeditor = CKEditor()
ckeditor.init_app(app)
Bootstrap5(app)

# TODO: Configure Flask-Login
login_manager=LoginManager()
login_manager.init_app(app)

# callabck to load user from session
@login_manager.user_loader
def load_user(id):
    return  db.get_or_404(User, int(id))

# CREATE DATABASE
class Base(DeclarativeBase):
    pass
# your app will use a production database if DB_URI is set, or local SQLite for development.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DB_URI",
    f"sqlite:///{os.path.join(basedir, 'instance', 'posts.db')}"
)
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
# TODO: Create a User table for all your registered users. 
class User(UserMixin,db.Model):#parent
    __tablename__="user"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    name: Mapped[str]=mapped_column(String(250),nullable=False)
    email: Mapped[str]=mapped_column(String(250),nullable=False, unique=True)
    password: Mapped[str]=mapped_column(String(250),nullable=False)
    # relations
    posts: Mapped[list["BlogPost"]]=relationship(back_populates="author")
    comments: Mapped[list["Comment"]]=relationship(back_populates="comment_author")
    
class BlogPost(db.Model):#child
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    
    # querying db for creating foreign key so in sql the tables are stored in lowercase so we use "user.id" instead of "User.id" 
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("user.id"))
    # relations
    author: Mapped["User"] = relationship(back_populates="posts")
    comments: Mapped["Comment"]=relationship(back_populates="parent_post")
    
class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    text: Mapped[str]=mapped_column(String(500),nullable=False)
    
    author_id: Mapped[int]=mapped_column(Integer,db.ForeignKey("user.id"))
    comment_author: Mapped["User"]=relationship(back_populates="comments")
    
    post_id: Mapped[int]=mapped_column(Integer,db.ForeignKey("blog_posts.id"))
    parent_post: Mapped["BlogPost"]=relationship(back_populates="comments") 
with app.app_context():
    db.create_all()

#GRAVATAR
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

#admin_only PYTHON DECORATOR
def admin_only(func):
    # It copies the metadata of func → into wrapper.
    @wraps(func)
    def wrapper_func(*args,**kwargs):
        if not current_user.id==1 or not current_user.is_authenticated:
            return render_template('forbidden.html')
        return func(*args,**kwargs)
    return wrapper_func

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register',methods=["GET","POST"])
def register():
    regform=RegisterForm()
    if regform.validate_on_submit():
        email=request.form.get("email")
        user=db.session.execute(db.select(User).where(User.email==email)).scalar_one_or_none()
        if user:
            flash("Email already exists. Login Instead!!")
            return redirect(url_for('login'))
        hashSalt=generate_password_hash(request.form.get("password"),method="pbkdf2:sha256", salt_length=8)
        new_user=User(name=regform.name.data,
                      email=request.form.get("email"),
                      password=hashSalt)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html",regform=regform)

# TODO: Retrieve a user from the database based on their email. 
@app.route('/login',methods=["GET","POST"])
def login():
    form=LoginForm()
    if form.validate_on_submit():
        user=db.session.execute(db.select(User).where(User.email==form.email.data)).scalar_one_or_none()
        if not user:
            flash("User doesn't exist. Check the email entered.")
            return redirect(url_for('login'))
            
        elif not check_password_hash(user.password, form.password.data):
            flash("Inncorrect password. Please try again.")
            return redirect(url_for('login'))
        else:
            # Logs a user in. You should pass the actual user object to this. 
            login_user(user)
            return redirect(url_for('get_all_posts'))
    return render_template("login.html",form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>",methods=["GET","POST"])
def show_post(post_id):
    form=CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    comments=db.session.execute(db.select(Comment).where(Comment.post_id==post_id)).scalars().all()
    if form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment=Comment(text=form.comment.data,author_id=current_user.id,post_id=post_id)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('show_post',post_id=post_id))
        else:
            flash("login to continue")
            return redirect(url_for('login'))
    return render_template("post.html", post=requested_post,form=form,comments=comments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])

def add_new_post():
    if current_user.is_authenticated and current_user.id==1:
        form = CreatePostForm()
        if form.validate_on_submit():
            new_post = BlogPost(
                title=form.title.data,
                subtitle=form.subtitle.data,
                body=form.body.data,
                img_url=form.img_url.data,
                author=current_user,
                date=date.today().strftime("%B %d, %Y")
            )
            db.session.add(new_post)
            db.session.commit()
            return redirect(url_for("get_all_posts"))
        return render_template("make-post.html", form=form)
    else:
        return render_template('forbidden.html')

# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
# @admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    if current_user.is_authenticated and current_user.email==post.author.email:
        
        edit_form = CreatePostForm(
            title=post.title,
            subtitle=post.subtitle,
            img_url=post.img_url,
            author=post.author,
            body=post.body
        )
        if edit_form.validate_on_submit():
            post.title = edit_form.title.data
            post.subtitle = edit_form.subtitle.data
            post.img_url = edit_form.img_url.data
            post.author = current_user
            post.body = edit_form.body.data
            db.session.commit()
            return redirect(url_for("show_post", post_id=post.id))
    
        return render_template("make-post.html", form=edit_form, is_edit=True)
    else:
        return render_template('forbidden.html')


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
# @admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    if current_user.is_authenticated and current_user.email==post_to_delete.author.email:
        db.session.delete(post_to_delete)
        db.session.commit()
        return redirect(url_for('get_all_posts'))
    else:
        return render_template('forbidden.html')


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact",methods=["GET","POST"])
def contact():
    if request.method=="GET":
        return render_template("contact.html")
    elif request.method=="POST":
        name=request.form['name']
        email=request.form['email']
        phone=request.form['phone']
        messg=request.form['message']
        with smtplib.SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(MY_EMAIL,PASSWORD)
            connection.sendmail(from_addr=MY_EMAIL,#my email can't send from someone else's mail
                                to_addrs=MY_EMAIL,#my email- can send to someone else's mail
                                msg=f"Subject:Likhi's Blog Contact\n\nName: {name}\nEmail:{email}\nPhone:{phone}\nMessage:{messg}")
        return render_template("contact.html",success=True)
    



if __name__ == "__main__":
    app.run(debug=True, port=5002)
