import os, json, base64, hashlib, uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secure_key_999')

# База даних
project_dir = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///" + os.path.join(project_dir, "shop.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Моделі
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Integer)
    img = db.Column(db.String(10))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(100))
    items = db.Column(db.String(500))
    total = db.Column(db.Integer)
    status = db.Column(db.String(20), default='Очікує оплати')

with app.app_context():
    db.create_all()
    # Початкові товари
    if not Product.query.first():
        db.session.add_all([
            Product(name="Локшина слабоостра", price=100, img="🍀"),
            Product(name="Локшина середньоостра", price=120, img="🔥"),
            Product(name="Локшина суперостра", price=150, img="💀")
        ])
    # Дефолтний адмін
    if not User.query.filter_by(email="admin@test.com").first():
        db.session.add(User(name="Адмін", email="admin@test.com", password="123", role="admin"))
    db.session.commit()

# --- МАРШРУТИ ---

@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        if User.query.filter_by(email=email).first():
            flash('Цей Email вже зайнятий!', 'danger')
        else:
            new_user = User(name=request.form.get('name'), email=email, password=request.form.get('password'))
            db.session.add(new_user)
            db.session.commit()
            flash('Успішна реєстрація!', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email'), password=request.form.get('password')).first()
        if user:
            session.update({'u_id': user.id, 'u_name': user.name, 'u_role': user.role, 'u_email': user.email})
            return redirect(url_for('index'))
        flash('Невірні дані', 'danger')
    return render_template('login.html')

@app.route('/add/<int:pid>')
def add_to_cart(pid):
    cart = session.get('cart', [])
    cart.append(pid)
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('index'))

@app.route('/cart')
def cart():
    cart_ids = session.get('cart', [])
    items = [Product.query.get(pid) for pid in cart_ids]
    total = sum(i.price for i in items if i)
    return render_template('cart.html', items=items, total=total)

@app.route('/checkout_liqpay', methods=['POST'])
def checkout_liqpay():
    cart_ids = session.get('cart', [])
    if not cart_ids: return redirect(url_for('index'))
    items = [Product.query.get(pid) for pid in cart_ids if Product.query.get(pid)]
    items_names = ", ".join([i.name for i in items])
    total = sum(i.price for i in items)
    
    order = Order(user_email=session.get('u_email'), items=items_names, total=total)
    db.session.add(order)
    db.session.commit()
    session.pop('cart', None)

    params = {
        "public_key": os.environ.get('LIQPAY_PUBLIC_KEY', 'sandbox_i0000000'),
        "version": "3", "action": "pay", "currency": "UAH",
        "amount": float(total), "description": f"Order #{order.id}",
        "order_id": str(order.id), "sandbox": "1"
    }
    data = base64.b64encode(json.dumps(params).encode()).decode()
    p_key = os.environ.get('LIQPAY_PRIVATE_KEY', 'sandbox_pass')
    signature = base64.b64encode(hashlib.sha1((p_key + data + p_key).encode()).digest()).decode()
    return render_template('redirect_liqpay.html', data=data, signature=signature)

# --- АДМІН ФУНКЦІЇ ---

@app.route('/admin')
def admin_panel():
    if session.get('u_role') != 'admin': return redirect(url_for('index'))
    return render_template('admin.html', users=User.query.all(), orders=Order.query.all(), products=Product.query.all())

@app.route('/admin/edit_product/<int:pid>', methods=['POST'])
def edit_product(pid):
    if session.get('u_role') == 'admin':
        product = Product.query.get(pid)
        product.name = request.form.get('name')
        product.price = int(request.form.get('price'))
        db.session.commit()
        flash('Товар оновлено!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
