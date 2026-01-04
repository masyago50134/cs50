import os, json, base64, hashlib, uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy


def _b64(s: bytes) -> str:
    return base64.b64encode(s).decode('utf-8')


def liqpay_signature(private_key: str, data_b64: str) -> str:
    """LiqPay signature = base64(sha1(private_key + data + private_key))."""
    sign_str = (private_key + data_b64 + private_key).encode('utf-8')
    return _b64(hashlib.sha1(sign_str).digest())


def liqpay_is_sandbox(pub_key: str) -> bool:
    # Explicit override via env, otherwise infer from key prefix
    env_val = os.environ.get('LIQPAY_SANDBOX')
    if env_val is not None:
        return env_val.strip() in {'1', 'true', 'True', 'yes', 'YES'}
    return pub_key.startswith('sandbox_')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_777')

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

# Ініціалізація бази
with app.app_context():
    db.create_all()
    if not Product.query.first():
        db.session.add_all([
            Product(name="Локшина слабоостра", price=100, img="🍀"),
            Product(name="Локшина середньоостра", price=120, img="🔥"),
            Product(name="Локшина суперостра", price=150, img="💀")
        ])
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
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email вже зайнятий', 'danger')
        else:
            new_user = User(name=name, email=email, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash('Реєстрація успішна!', 'success')
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
    items = [Product.query.get(pid) for pid in cart_ids if Product.query.get(pid)]
    total = sum(i.price for i in items)
    return render_template('cart.html', items=items, total=total)


@app.route('/clear')
def clear_cart():
    session.pop('cart', None)
    session.modified = True
    flash('Кошик очищено', 'info')
    return redirect(url_for('cart'))

@app.route('/checkout_liqpay', methods=['POST'])
def checkout_liqpay():
    cart_ids = session.get('cart', [])
    if not cart_ids:
        flash('Кошик порожній!', 'warning')
        return redirect(url_for('index'))
    
    # Знаходимо реальні об'єкти товарів у базі
    items = []
    for pid in cart_ids:
        p = Product.query.get(pid)
        if p:
            items.append(p)
    
    if not items:
        session.pop('cart', None)
        flash('Товари не знайдені в базі', 'danger')
        return redirect(url_for('index'))

    items_names = ", ".join([i.name for i in items])
    total = sum(i.price for i in items)
    
    # 1. Створюємо замовлення
    order = Order(user_email=session.get('u_email', 'Гість'), items=items_names, total=total)
    db.session.add(order)
    db.session.commit()

    # Запам'ятовуємо замовлення для поточного користувача (щоб очистити кошик після підтвердження)
    session['pending_order_id'] = order.id
    session.modified = True
    
    # 2. НЕ очищуємо кошик одразу: користувач може повернутися та повторити оплату.
    #    Очищення робимо після успішного callback від LiqPay.

    # 3. Формуємо LiqPay (використовуємо .get для безпеки)
    pub_key = os.environ.get('LIQPAY_PUBLIC_KEY', 'sandbox_i0000000')
    priv_key = os.environ.get('LIQPAY_PRIVATE_KEY', 'sandbox_pass')

    # Робимо order_id унікальним (LiqPay не любить повтори)
    liqpay_order_id = f"{order.id}-{uuid.uuid4().hex[:8]}"

    params = {
        "public_key": pub_key,
        "version": "3",
        "action": "pay",
        "amount": f"{total:.2f}",
        "currency": "UAH",
        "description": f"Замовлення №{order.id}: {items_names[:100]}",
        "order_id": liqpay_order_id,
        # Куди повернути користувача після оплати
        "result_url": url_for('payment_return', order_id=order.id, _external=True),
        # Серверний callback (оновлюємо статус замовлення)
        "server_url": url_for('liqpay_callback', _external=True),
    }

    if liqpay_is_sandbox(pub_key):
        params["sandbox"] = 1

    # Важливо: використовуємо json.dumps без зайвих пробілів
    json_params = json.dumps(params, separators=(',', ':'))
    data = _b64(json_params.encode('utf-8'))
    signature = liqpay_signature(priv_key, data)
    
    return render_template('redirect_liqpay.html', data=data, signature=signature)


@app.route('/payment_return/<int:order_id>')
def payment_return(order_id: int):
    order = Order.query.get(order_id)
    if not order:
        abort(404)

    # Якщо статус вже підтверджено, і це замовлення поточного користувача — очищаємо кошик
    if order.status == 'Оплачено' and session.get('pending_order_id') == order.id:
        session.pop('cart', None)
        session.pop('pending_order_id', None)
        session.modified = True
    return render_template('payment_return.html', order=order)


@app.route('/liqpay_callback', methods=['POST'])
def liqpay_callback():
    """Callback endpoint for LiqPay. Updates order status.

    LiqPay sends form-encoded fields: data, signature.
    """
    data_b64 = request.form.get('data', '')
    signature = request.form.get('signature', '')

    pub_key = os.environ.get('LIQPAY_PUBLIC_KEY', 'sandbox_i0000000')
    priv_key = os.environ.get('LIQPAY_PRIVATE_KEY', 'sandbox_pass')

    # 1) Verify signature
    expected = liqpay_signature(priv_key, data_b64)
    if not data_b64 or not signature or signature != expected:
        # Не даємо деталей назовні
        return 'bad signature', 400

    # 2) Decode payload
    try:
        payload = json.loads(base64.b64decode(data_b64).decode('utf-8'))
    except Exception:
        return 'bad payload', 400

    liqpay_order_id = str(payload.get('order_id', ''))
    status = str(payload.get('status', '')).lower()

    # Наш order_id: "<db_id>-<random>"
    try:
        order_db_id = int(liqpay_order_id.split('-')[0])
    except Exception:
        return 'unknown order', 400

    order = Order.query.get(order_db_id)
    if not order:
        return 'order not found', 404

    # 3) Update status
    # Корисні статуси: success, sandbox, failure, error, reversed, refunded, etc.
    if status in {'success', 'sandbox'}:
        order.status = 'Оплачено'
    elif status in {'failure', 'error'}:
        order.status = 'Оплата неуспішна'
    else:
        # pending / wait_accept / processing / etc.
        order.status = f'Статус: {status}'

    db.session.commit()
    return 'OK'


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

# Додавання нового товару
@app.route('/admin/add_product', methods=['POST'])
def add_product():
    if session.get('u_role') == 'admin':
        name = request.form.get('name')
        price = int(request.form.get('price'))
        img = request.form.get('img', '🍜') # Емодзі за замовчуванням
        
        new_product = Product(name=name, price=price, img=img)
        db.session.add(new_product)
        db.session.commit()
        flash(f'Товар "{name}" додано!', 'success')
    return redirect(url_for('admin_panel'))

# Видалення товару
@app.route('/admin/delete_product/<int:pid>')
def delete_product(pid):
    if session.get('u_role') == 'admin':
        product = Product.query.get(pid)
        if product:
            db.session.delete(product)
            db.session.commit()
            flash('Товар видалено', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))


