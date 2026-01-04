import os
import json
import base64
import hashlib
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secure_key_999')

# Налаштування бази даних SQLite
project_dir = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///" + os.path.join(project_dir, "shop.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Моделі бази даних
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')

# Дані товарів (статичні для простоти)
PRODUCTS = {
    1: {"name": "Локшина слабоостра", "price": 100, "img": "🍀", "desc": "Легкий пікантний смак"},
    2: {"name": "Локшина середньоостра", "price": 120, "img": "🔥", "desc": "Для поціновувачів гострого"},
    3: {"name": "Локшина суперостра", "price": 150, "img": "💀", "desc": "Тільки для сміливців!"}
}

# Створення бази при запуску
with app.app_context():
    db.create_all()
    # Створюємо адміна за замовчуванням, якщо його немає
    if not User.query.filter_by(email="admin@test.com").first():
        admin = User(name="Адмін", email="admin@test.com", password="123", role="admin")
        db.session.add(admin)
        db.session.commit()

# --- МАРШРУТИ ---

@app.route('/')
def index():
    return render_template('index.html', products=PRODUCTS)

@app.route('/admin')
def admin_panel():
    # Перевірка прав доступу
    if 'u_role' not in session or session['u_role'] != 'admin':
        flash('Доступ заборонено! Ви не є адміністратором.', 'danger')
        return redirect(url_for('index'))
    
    # Отримуємо всіх користувачів з бази даних
    users = User.query.all()
    return render_template('admin.html', users=users, products=PRODUCTS)
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Цей Email вже зареєстровано', 'danger')
        else:
            new_user = User(name=name, email=email, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash('Реєстрація успішна! Увійдіть.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            session.update({'u_id': user.id, 'u_name': user.name, 'u_role': user.role})
            return redirect(url_for('index'))
        flash('Невірні дані входу', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/add/<int:pid>')
def add_to_cart(pid):
    if 'u_id' not in session:
        flash('Увійдіть, щоб додати товар', 'warning')
        return redirect(url_for('login'))
    cart = session.get('cart', [])
    cart.append(pid)
    session['cart'] = cart
    return redirect(url_for('index'))

@app.route('/cart')
def cart():
    cart_ids = session.get('cart', [])
    items = [PRODUCTS[pid] for pid in cart_ids if pid in PRODUCTS]
    total = sum(i['price'] for i in items)
    
    data, signature = "", ""
    if total > 0:
        params = {
            "public_key": os.environ.get('LIQPAY_PUBLIC_KEY', 'sandbox_key'),
            "version": "3", "action": "pay", "currency": "UAH",
            "amount": float(total), "description": "Оплата замовлення",
            "order_id": str(uuid.uuid4()), "sandbox": "1"
        }
        data = base64.b64encode(json.dumps(params).encode()).decode()
        p_key = os.environ.get('LIQPAY_PRIVATE_KEY', 'sandbox_p_key')
        signature = base64.b64encode(hashlib.sha1((p_key + data + p_key).encode()).digest()).decode()
        
    return render_template('cart.html', items=items, total=total, data=data, signature=signature)

@app.route('/clear')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('cart'))

if __name__ == '__main__':
    app.run(debug=True)

