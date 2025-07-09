from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import datetime
from flask import abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests ### NEW ###
import uuid ### NEW ###
import json ### NEW ###
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# ✅ Setup limiter (limit based on IP address)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

### NEW ### - Payment Gateway Configuration
PAYMENT_GATEWAY_TOKEN = "S41ZLPLR6nS2kg" # As specified in your curl command

PAYMENT_SERVICE_HOSTNAME = os.environ.get('PAYMENT_SERVICE_HOST', '127.0.0.1')
PAYMENT_GATEWAY_URL = f"http://{PAYMENT_SERVICE_HOSTNAME}:8001/api/create-payment"

def get_public_url(port):
    """
    Dynamically constructs the public URL for a given port.
    Detects if running in a GitHub Codespace and builds the URL accordingly.
    Falls back to localhost for local development.
    """
    # Check for Codespace-specific environment variables
    if 'CODESPACE_NAME' in os.environ and 'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN' in os.environ:
        codespace_name = os.environ['CODESPACE_NAME']
        domain = os.environ['GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN']
        return f"https://{codespace_name}-{port}.{domain}"
    else:
        # Fallback for local development
        print("ITS LOCAL")
        return f"http://localhost:{port}"


# Database setup
def init_db():
    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                access TEXT DEFAULT 'user' NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL CHECK (LENGTH(content) <= 255),
                profile_pic TEXT,
                date TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 5),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total_amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price_at_purchase REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        # This check prevents re-inserting data on every startup
        cursor.execute("SELECT COUNT(*) FROM sqlite_sequence WHERE name='products'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('products', 0)")
        
        conn.commit()

        # Add example products if the table is empty
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        
        if product_count == 0:
            example_products = [
                ('تی شرت بردان', 'تی‌شرتی سبک و راحت با طراحی مدرن که از پارچه باکیفیت و ضدحساسیت تهیه شده است. مناسب برای استفاده روزمره، ورزش و استایل کژوال. دارای دوخت مقاوم و رنگ‌بندی متنوع برای سلیقه‌های مختلف. به‌راحتی شسته شده و کیفیت پارچه پس از شستشو حفظ می‌شود. انتخابی عالی برای افرادی که به استایل و راحتی اهمیت می‌دهند.', 21000),
                ('کوله پشتی', 'یک کوله‌پشتی مدرن با طراحی ارگونومیک و فضای کافی برای حمل وسایل روزانه. دارای چندین جیب مجزا برای نظم‌دهی بهتر و حمل لپ‌تاپ، کتاب و لوازم شخصی. ساخته‌شده از مواد مقاوم در برابر آب و سایش برای دوام بیشتر. دارای بندهای قابل تنظیم و پدگذاری شده برای راحتی بیشتر در حمل. گزینه‌ای عالی برای دانشجویان، مسافران و افراد پرمشغله.', 250000),
                ('ساعت الگنت', 'یک ساعت شیک و مدرن که زیبایی و کارایی را در کنار هم ارائه می‌دهد. طراحی ظریف و منحصر‌به‌فرد آن مناسب برای استفاده روزمره و موقعیت‌های رسمی است. دارای صفحه‌ای خوانا و بند مقاوم برای استفاده طولانی‌مدت. موتور باکیفیت و دقیق که زمان را با دقت بالا نمایش می‌دهد. انتخابی عالی برای افرادی که به استایل و دقت اهمیت می‌دهند.', 50000),
                ('کوله سبک', 'یک کوله‌پشتی فوق سبک و کم‌حجم که برای حمل آسان طراحی شده است. مناسب برای افرادی که به دنبال راحتی بیشتر و آزادی حرکت هستند. ساخته‌شده از پارچه مقاوم و ضدآب، ایده‌آل برای استفاده روزانه و سفرهای کوتاه. دارای زیپ‌های روان و جیب‌های کاربردی برای حمل وسایل ضروری. بهترین انتخاب برای افرادی که به مینیمالیسم و کارایی اهمیت می‌دهند.', 180000),
                ('لباس چرم', 'یک لباس چرم باکیفیت که ظاهری شیک و کلاسیک را به استایل شما می‌بخشد. تهیه‌شده از چرم طبیعی یا مصنوعی مقاوم، مناسب برای فصول سرد سال. دارای طراحی مدرن با جزئیات خاص که ظاهری جذاب و لوکس ایجاد می‌کند. دوخت محکم و دقیق که دوام و ماندگاری لباس را تضمین می‌کند. مناسب برای موقعیت‌های رسمی و نیمه‌رسمی، ایده‌آل برای علاقه‌مندان به مد.', 200000),
                ('لباس کودک', 'یک لباس نرم و راحت برای کودکان، ساخته‌شده از الیاف ضدحساسیت. طراحی زیبا و رنگ‌های جذاب که برای کودکان دلنشین و دوست‌داشتنی است. دارای دوخت بادوام که امکان شستشوی مکرر بدون آسیب به بافت پارچه را فراهم می‌کند. سبک و انعطاف‌پذیر، مناسب برای فعالیت‌های روزانه کودک. انتخابی ایده‌آل برای راحتی و سلامت پوست حساس کودکان.', 300000),
                ('هدفون سونی', 'یک هدفون باکیفیت که تجربه‌ای عالی از موسیقی و تماس‌های صوتی را فراهم می‌کند. دارای قابلیت حذف نویز برای ایجاد صدایی واضح و شفاف در محیط‌های شلوغ. طراحی ارگونومیک و سبک که راحتی را برای استفاده طولانی‌مدت تضمین می‌کند. مجهز به باتری بادوام و قابلیت اتصال بی‌سیم برای آزادی حرکت بیشتر. مناسب برای گوش دادن به موسیقی، گیمینگ و استفاده روزمره.', 100000),
                ('کیف چرم', 'یک کیف چرم شیک و باکیفیت که استایل لوکس و حرفه‌ای را به شما می‌بخشد. ساخته‌شده از چرم طبیعی یا مصنوعی مقاوم، مناسب برای استفاده روزانه و رسمی. دارای بخش‌های مجزا برای حمل لپ‌تاپ، مدارک و وسایل شخصی. زیپ‌های مقاوم و دوخت بادوام که طول عمر کیف را افزایش می‌دهد. گزینه‌ای ایده‌آل برای افراد شیک‌پوش و حرفه‌ای که به کیفیت اهمیت می‌دهند.', 1300000)
            ]
            cursor.executemany("INSERT INTO products (name, description, price) VALUES (?, ?, ?)", example_products)
            conn.commit()
            example_comments = [
                (1, 'علی رضایی', 'تی‌شرت خیلی راحت و سبک بود، کیفیتش هم خیلی خوبه.', '/static/images/user/default.png', '2025-02-08', 5),
                (1, 'مریم احمدی', 'پارچه خیلی لطیف و خوش دوخت، ولی رنگش کمی متفاوت بود.', '/static/images/user/default.png', '2025-02-07', 4),
                (2, 'حسن کریمی', 'کوله‌پشتی جاداره و جنس خوبی داره، ولی زیپ‌هاش یکم سفته.', '/static/images/user/default.png', '2025-02-06', 4),
                (3, 'سارا بهرامی', 'ساعت خیلی شیک و سبک هست، از خریدش خیلی راضیم.', '/static/images/user/default.png', '2025-02-05', 5),
                (4, 'رضا معتمدی', 'کوله‌پشتی خیلی سبکه و حملش راحته، ولی میتونست جیب بیشتری داشته باشه.', '/static/images/user/default.png', '2025-02-04', 3),
                (5, 'نرگس صادقی', 'کیفیت چرم عالیه، خیلی خوش‌دوخت و زیباست.', '/static/images/user/default.png', '2025-02-03', 5),
                (6, 'امیر فراهانی', 'لباس کودک نرم و راحت، ولی سایزش کمی بزرگ‌تر از حد انتظار بود.', '/static/images/user/default.png', '2025-02-02', 4),
                (7, 'زهرا محمدی', 'هدفون صدای خیلی خوبی داره، ولی باتریش میتونست بهتر باشه.', '/static/images/user/default.png', '2025-02-01', 4),
                (8, 'کامران کاظمی', 'کیف چرم بسیار زیبا و شیک، ولی کمی گرونه.', '/static/images/user/default.png', '2025-01-31', 4)
            ]
            cursor.executemany("INSERT INTO comments (product_id, name, content, profile_pic, date, score) VALUES (?, ?, ?, ?, ?, ?)", example_comments)
            conn.commit()


### NEW ### - Context Processor to make cart count available to all templates
@app.context_processor
def utility_processor():
    def cart_item_count():
        return sum(session.get('cart', {}).values()) if 'username' in session else 0
    return dict(cart_item_count=cart_item_count)

@app.route('/')
def home():
    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
    return render_template('home.html', products=products)

@app.route('/products')
def product_list():
    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
    return render_template('product_list.html', products=products)


@app.route('/product/<int:product_id>')  # Flask will now enforce integer-only IDs
def product_detail(product_id):
    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()

        # Secure: Use parameterized query
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if product is None:
            abort(404)

        cursor.execute("""
            SELECT name, content, profile_pic, date, score 
            FROM comments 
            WHERE product_id = ?
        """, (product_id,))
        comments = cursor.fetchall()

        cursor.execute("""
            SELECT * FROM products 
            WHERE id != ? 
            ORDER BY RANDOM() 
            LIMIT 5
        """, (product_id,))
        other_products = cursor.fetchall()

    return render_template(
        'product_detail.html',
        product=product,
        comments=comments,
        other_products=other_products
    )



@app.route('/product/<int:product_id>/comment', methods=['POST'])
def submit_comment(product_id):
    name = session.get('username', 'Anonymous')
    content = request.form.get('message')
    score = request.form.get('star', 0)  # Default to 0 if not provided
    profile_pic = "/static/images/user/default.png"  # You can replace this with an actual profile image path
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO comments (product_id, name, content, profile_pic, date, score) VALUES (?, ?, ?, ?, ?, ?)", 
                       (product_id, name, content, profile_pic, date, score))
        conn.commit()

    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("تعداد درخواست بیش از حد")
def login():
    login_failed = False
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect("app.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
            if user:
                session['username'] = user[1]  # Assuming the second column is the username
                session['cart'] = {} # ### NEW ### Initialize empty cart on login
                flash('Login successful!', 'success')
                return redirect(url_for('profile'))
            else:
                login_failed = True
    return render_template('login.html', login_failed=login_failed)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("تعداد درخواست بیش از حد")  # ✅ Apply rate limit
def register():
    user_exists = False
    registration_successful = False

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect("app.db") as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
                registration_successful = True
            except sqlite3.IntegrityError:
                # Username exists, but we won't explicitly tell the user
                user_exists = True  # We won't show this to prevent enumeration

        # ✅ Show generic message
        if registration_successful:
            flash('Registration completed.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Registration could not be completed.', 'danger')

    return render_template('register.html',user_exists=user_exists)

@app.route('/profile')
def profile():
    if 'username' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))
    
    username = session['username']
    user_data = None
    orders = {} # Use a dictionary to group items by order

    with sqlite3.connect("app.db") as conn:
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        cursor = conn.cursor()
        
        # Get user info
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user:
            user_data = dict(user)
            
            # Fetch all order items for this user, joining all necessary tables
            query = """
                SELECT 
                    o.id as order_id,
                    o.created_at,
                    o.total_amount,
                    p.name as product_name,
                    oi.quantity,
                    oi.price_at_purchase
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                JOIN products p ON oi.product_id = p.id
                WHERE o.user_id = ?
                ORDER BY o.created_at DESC, p.name
            """
            cursor.execute(query, (user_data['id'],))
            order_items_list = cursor.fetchall()
            
            # Group the items by order_id
            for item in order_items_list:
                order_id = item['order_id']
                if order_id not in orders:
                    orders[order_id] = {
                        'id': order_id,
                        'created_at': datetime.datetime.strptime(item['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d'),
                        'total_amount': item['total_amount'],
                        # --- FIX: Renamed 'items' to 'products' ---
                        'products': []
                    }
                # --- FIX: Appending to 'products' ---
                orders[order_id]['products'].append(dict(item))

    if not user_data:
        return redirect(url_for('logout')) # Failsafe if user doesn't exist

    # This line is now correct and will work with the renamed key
    return render_template('profile.html', user=user_data, orders=list(orders.values()))


@app.route("/about-us")
def about_us():
    return render_template('about-us.html')

@app.route('/logout')
def logout():
    # Clear the user session
    session.pop('username', None)
    session.pop('cart', None) ### NEW ### Clear cart on logout
    # Redirect to the home page
    return redirect('/')

### NEW ### - Shopping Cart Routes

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'username' not in session:
        flash('لطفا برای اضافه کردن محصول به سبد خرید، ابتدا وارد شوید.', 'warning')
        return redirect(url_for('login'))

    # VULNERABILITY: Switched from int() to float() and removed validation.
    # The application now accepts fractional quantities like 0.1, -5, etc.
    # A robust application should check if the quantity is a positive integer.
    try:
        quantity = float(request.form.get('quantity', 1.0))
    except (ValueError, TypeError):
        # If the input isn't a number at all, just default to 1.
        quantity = 1.0

    # Ensure cart exists in session
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    # Use string for product_id as JSON keys are strings
    str_product_id = str(product_id)

    # Add item to cart
    # The cart will now store quantities like 0.1, 1.5, etc.
    cart[str_product_id] = cart.get(str_product_id, 0.0) + quantity
    session['cart'] = cart  # Save cart back to session

    flash(f'{quantity} عدد از محصول به سبد خرید شما اضافه شد.', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def view_cart():
    if 'username' not in session:
        flash('لطفا برای مشاهده سبد خرید خود، ابتدا وارد شوید.', 'warning')
        return redirect(url_for('login'))
        
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0.0

    if cart:
        # Validate quantities before using them
        sanitized_cart = {}
        for product_id, quantity in cart.items():
            try:
                quantity_int = int(quantity)
                if quantity_int > 0:
                    sanitized_cart[str(product_id)] = quantity_int
                else:
                    flash(f"مقدار نامعتبر برای محصول {product_id}.", "danger")
            except (ValueError, TypeError):
                flash(f"مقدار نامعتبر برای محصول {product_id}.", "danger")

        product_ids = sanitized_cart.keys()

        with sqlite3.connect("app.db") as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in product_ids)
            query = f"SELECT id, name, price, description FROM products WHERE id IN ({placeholders})"
            cursor.execute(query, list(product_ids))
            products = cursor.fetchall()
            product_map = {str(p[0]): p for p in products}

            for product_id, quantity in sanitized_cart.items():
                product_data = product_map.get(product_id)
                if product_data:
                    subtotal = product_data[2] * quantity
                    total_price += subtotal
                    cart_items.append({
                        'product': product_data,
                        'quantity': quantity,
                        'subtotal': subtotal
                    })

    return render_template('cart.html', cart_items=cart_items, total_price=total_price)


@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    cart.pop(str(product_id), None) # Remove item, do nothing if not found
    session['cart'] = cart

    flash('محصول از سبد خرید شما حذف شد.', 'info')
    return redirect(url_for('view_cart'))

@app.route('/update_cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    quantity = int(request.form.get('quantity', 0))
    cart = session.get('cart', {})
    
    if quantity > 0:
        cart[str(product_id)] = quantity
        flash('تعداد محصول بروزرسانی شد.', 'success')
    else:
        cart.pop(str(product_id), None)
        flash('محصول از سبد خرید شما حذف شد.', 'info')

    session['cart'] = cart
    return redirect(url_for('view_cart'))

### NEW ### - Payment Gateway Routes

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'username' not in session:
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    if not cart:
        flash('سبد خرید شما خالی است.', 'warning')
        return redirect(url_for('view_cart'))

    # Recalculate total price on the server-side to ensure accuracy
    total_price = 0
    product_ids = cart.keys()
    with sqlite3.connect("app.db") as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in product_ids)
        query = f"SELECT id, price FROM products WHERE id IN ({placeholders})"
        cursor.execute(query, list(product_ids))
        products = cursor.fetchall()
        product_map = {str(p[0]): p[1] for p in products}

        for product_id, quantity in cart.items():
            total_price += product_map.get(product_id, 0) * quantity
    
    if total_price <= 0:
        flash('مبلغ قابل پرداخت باید بیشتر از صفر باشد.', 'danger')
        return redirect(url_for('view_cart'))
        
    # Generate a unique code for this transaction
    transaction_code = uuid.uuid4().hex
    session['transaction_code'] = transaction_code # Store for verification

    # --- DYNAMIC URL LOGIC ---
    # 1. Construct the full, public callback URL for THIS application (on port 8080)
    public_self_url = get_public_url(8080)
    full_callback_url = f"{public_self_url}{url_for('payment_verify')}"


    # Prepare data for the payment gateway API
    payload = {
        "token": PAYMENT_GATEWAY_TOKEN,
        "price": str(total_price),
        "code": transaction_code,
        "callback": full_callback_url # Send the dynamically generated URL
    }
    
    try:
        # This request happens server-to-server (webserver -> paymentserver)
        response = requests.post(PAYMENT_GATEWAY_URL, json=payload, timeout=10)
        response.raise_for_status()

        response_data = response.json()
        
        if 'url' in response_data:
            # 2. Construct the full, public redirect URL for the PAYMENT service (on port 8001)
            public_payment_url = get_public_url(8001)
            payment_redirect_url = f"{public_payment_url}{response_data['url']}"
            
            return redirect(payment_redirect_url)
        else:
            error_message = response_data.get('error', 'Unknown error from payment gateway.')
            flash(f'Error creating payment: {error_message}', 'danger')
            return redirect(url_for('view_cart'))

    except requests.exceptions.RequestException as e:
        flash(f'Could not connect to the payment service: {e}', 'danger')
        return redirect(url_for('view_cart'))
 
@app.route('/payment_verify')
def payment_verify():
    payment_id = request.args.get('id')
    hash_value = request.args.get('hash')

    if not payment_id or not hash_value:
        flash('اطلاعات پرداخت ناقص است.', 'danger')
        return redirect(url_for('view_cart'))

    # Step 1: Verify payment with validator server
    try:
        public_self_url = get_public_url(8001)  # dynamic base URL
        verify_url = f"{public_self_url}/api/verify-payment"

        response = requests.post(
            verify_url,
            data={'id': payment_id, 'hash': hash_value},
            timeout=5
        )
        result = response.json()
        if response.status_code != 200 or result.get('status') != '1':
            flash('پرداخت تأیید نشد. لطفا دوباره تلاش کنید.', 'danger')
            return redirect(url_for('view_cart'))
    except requests.RequestException as e:
        print(f"Error verifying payment: {e}")
        flash('مشکلی در ارتباط با سرور پرداخت رخ داد.', 'danger')
        return redirect(url_for('view_cart'))

    # Step 2: Continue if verified
    try:
        with sqlite3.connect("app.db") as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
            user_row = cursor.fetchone()
            if not user_row:
                flash('کاربر یافت نشد.', 'danger')
                return redirect(url_for('view_cart'))
            user_id = user_row[0]

            cart = session.get('cart', {})
            if not cart:
                flash('سبد خرید شما خالی است.', 'warning')
                return redirect(url_for('home'))

            total_price = 0
            sanitized_cart = {}
            for product_id, quantity in cart.items():
                try:
                    quantity = int(quantity)
                    if quantity > 0:
                        sanitized_cart[str(product_id)] = quantity
                except (ValueError, TypeError):
                    continue

            product_ids = sanitized_cart.keys()
            placeholders = ','.join('?' for _ in product_ids)
            query = f"SELECT id, price FROM products WHERE id IN ({placeholders})"
            products = cursor.execute(query, list(product_ids)).fetchall()
            product_map = {str(p[0]): p[1] for p in products}

            for pid, quantity in sanitized_cart.items():
                total_price += product_map.get(pid, 0) * quantity

            cursor.execute(
                "INSERT INTO orders (user_id, total_amount, status) VALUES (?, ?, ?)",
                (user_id, total_price, 'success')
            )
            order_id = cursor.lastrowid

            for pid, quantity in sanitized_cart.items():
                price_at_purchase = product_map.get(pid, 0)
                cursor.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase) VALUES (?, ?, ?, ?)",
                    (order_id, int(pid), quantity, price_at_purchase)
                )
            
            conn.commit()

    except sqlite3.Error as e:
        print(f"Database error while saving order: {e}")
        flash('خطایی در ثبت سفارش شما رخ داد. لطفا با پشتیبانی تماس بگیرید.', 'danger')
        return redirect(url_for('view_cart'))

    # Step 3: Clear cart and show success
    session.pop('cart', None)
    session.pop('transaction_code', None)
    session.modified = True
    flash('پرداخت شما با موفقیت انجام شد. سفارش شما ثبت گردید.', 'success')
    return redirect(url_for('profile'))


if __name__ == '__main__':
    init_db()  # Initialize database
    app.run(host='0.0.0.0', port=8080, debug=True)