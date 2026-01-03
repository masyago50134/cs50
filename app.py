import os
import json
import base64
import hashlib
import uuid
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_123')

# ТЕСТОВІ КЛЮЧІ LIQPAY (працюють у sandbox режимі)
LIQPAY_PUBLIC_KEY = 'sandbox_i89454153096' 
LIQPAY_PRIVATE_KEY = 'sandbox_your_private_key' # В реальному проекті ховати в змінні оточення

PRODUCTS = {
    1: {"name": "Локшина слабоостра", "price": 100, "img": "🍀", "lvl": "Слабка"},
    2: {"name": "Локшина середньоостра", "price": 120, "img": "🔥", "lvl": "Середня"},
    3: {"name": "Локшина суперостра", "price": 150, "img": "💀", "lvl": "Пекельна"}
}

@app.route('/')
def index():
    return render_template('index.html', products=PRODUCTS)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['user'] = request.form.get('username')
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/add/<int:pid>')
def add_to_cart(pid):
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