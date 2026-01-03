import os
import json
import base64
import hashlib
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-123')

# Імітація бази даних (в реальному проекті використовуйте SQLAlchemy + Postgres)
# Ролі: 'admin' або 'user'
USERS = {
    "admin@test.com": {"password": "123", "name": "Адміністратор", "role": "admin"}
}

PRODUCTS = {
    1: {"name": "Локшина слабоостра", "price": 100, "img": "🍀"},
    2: {"name": "Локшина середньоостра", "price": 120, "img": "🔥"},
    3: {"name": "Локшина суперостра", "price": 150, "img": "💀"}
}

# --- МАРШРУТИ АВТОРИЗАЦІЇ ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if email in USERS:
            flash('Користувач з таким email вже існує!', 'danger')
        else:
            USERS[email] = {"password": password, "name": name, "role": "user"}
            flash('Реєстрація успішна! Тепер увійдіть.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = USERS.get(email)
        if user and user['password'] == password:
            session['user_email'] = email
            session['user_role'] = user['role']
            session['user_name'] = user['name']
            return redirect(url_for('index'))
        else:
            flash('Невірний email або пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- АДМІН-ПАНЕЛЬ ---

@app.route('/admin')
def admin_panel():
    if session.get('user_role') != 'admin':
        return "Доступ заборонено! Ви не адмін.", 403
    return render_template('admin.html', products=PRODUCTS, users=USERS)

# --- МАГАЗИН ТА КОШИК ---

@app.route('/')
def index():
    return render_template('index.html', products=PRODUCTS)

@app.route('/add/<int:pid>')
def add_to_cart(pid):
    if 'user_email' not in session:
        flash('Будь ласка, увійдіть в акаунт, щоб купувати', 'warning')
        return redirect(url_for('login'))
    
    if 'cart' not in session: session['cart'] = []
    session['cart'].append(pid)
    session.modified = True
    return redirect(url_for('index'))

@app.route('/cart')
def cart():
    ids = session.get('cart', [])
    items = [PRODUCTS[pid] for pid in ids if pid in PRODUCTS]
    total = sum(item['price'] for item in items)
    
    liqpay_data = ""
    signature = ""
    
    if total > 0:
        params = {
            "public_key": LIQPAY_PUBLIC_KEY,
            "version": "3",
            "action": "pay",
            "amount": str(total),
            "currency": "UAH",
            "description": f"Оплата замовлення локшини ({len(items)} шт)",
            "order_id": str(uuid.uuid4()),
            "sandbox": "1" 
        }
        json_params = json.dumps(params)
        liqpay_data = base64.b64encode(json_params.encode()).decode()
        sign_str = LIQPAY_PRIVATE_KEY + liqpay_data + LIQPAY_PRIVATE_KEY
        signature = base64.b64encode(hashlib.sha1(sign_str.encode()).digest()).decode()

    return render_template('cart.html', items=items, total=total, data=liqpay_data, signature=signature)

@app.route('/clear')
def clear_cart():
    session.pop('cart', None)
    return redirect(url_for('cart'))

if __name__ == '__main__':
    # Налаштування для локального запуску та хостингу
    port = int(os.environ.get("PORT", 5000))

    app.run(host='0.0.0.0', port=port)
