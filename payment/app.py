import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse

from flask import Flask, request, render_template, abort, jsonify, redirect

# --- SOLUTION: Centralize environment detection ---
# Use the same robust flags to understand our environment.
# Flag 1: Is the HOST machine a GitHub Codespace? (For public URLs)
IS_IN_CODESPACE = bool(os.environ.get('CODESPACE_NAME'))
# Flag 2: Is this process running inside a Docker container? (Not strictly needed
# in this file, but good practice to have available if you add service-to-service calls)
IS_IN_DOCKER = os.path.exists('/.dockerenv')
# --- END OF SOLUTION BLOCK ---

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'
app.config['hidden-token'] = 'S41ZLPLR6nS2kg'
DB_FILE = 'payments.db'


def get_public_url(port):
    """
    Dynamically constructs the public URL for a given port.
    This is the most reliable way to get the Codespace URL.
    Falls back to localhost for local development.
    """
    # Use the centralized flag for clean detection
    if IS_IN_CODESPACE:
        # Method 1: Use the pre-constructed URL from Codespaces (most reliable)
        public_url_var = f'CODESPACE_HOST_PORT_{port}_TCP_PUBLIC_URL'
        if public_url_var in os.environ:
            return f"https://{os.environ[public_url_var]}"

        # Method 2: Fallback to constructing the URL manually
        if 'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN' in os.environ:
            codespace_name = os.environ['CODESPACE_NAME']
            domain = os.environ['GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN']
            return f"https://{codespace_name}-{port}.{domain}"

    # Method 3: Fallback for local development
    return f"http://localhost:{port}"


def get_db():
    return sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)


def init_db():
    # ... (no changes needed here) ...
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            custom_hash TEXT UNIQUE,
            created_at TEXT,
            token TEXT,
            price TEXT,
            code TEXT,
            callback TEXT,
            status TEXT,
            card_number TEXT
        )
    ''')
    conn.commit()
    conn.close()


@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    data = request.json
    required = ['token', 'price', 'code', 'callback']
    if not all(k in data for k in required):
        return {"error": "Missing required fields"}, 400

    if data['token'] != app.config['hidden-token']:
        return {"error": "Invalid token"}, 403

    callback_url = data['callback']
    parsed_url = urlparse(callback_url)

    # --- SOLUTION: Robust, dynamic callback URL correction ---
    # We only need to fix the URL if the host is a Codespace AND the
    # calling service mistakenly sent a 'localhost' or '127.0.0.1' URL.
    if IS_IN_CODESPACE and parsed_url.hostname in ('localhost', '127.0.0.1'):
        
        # DYNAMIC PORT DETECTION: Instead of hardcoding a port like 8080,
        # we intelligently extract the port from the callback URL itself.
        # This makes the code robust even if the other service changes its port.
        client_port = parsed_url.port
        if not client_port:
            # Handle cases where port is not in URL (e.g. http://localhost/path)
            # Default to 80, but you might adjust this if needed.
             client_port = 80
             
        public_base_url = get_public_url(client_port)

        # Reconstruct the full callback URL, preserving the original path and query
        fixed_callback_url = parsed_url._replace(
            scheme="https", netloc=urlparse(public_base_url).netloc
        ).geturl()
        
        print(f"*** INFO: Corrected localhost callback from '{callback_url}' to '{fixed_callback_url}' ***")
        callback_url = fixed_callback_url  # Use the corrected URL

    # --- END OF SOLUTION BLOCK ---

    custom_hash = sha256(f"{uuid.uuid4()}_{data['token']}_{data['price']}_{data['code']}_{callback_url}".encode()).hexdigest()[:16]
    created_at = datetime.utcnow().isoformat()

    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO payments (custom_hash, created_at, token, price, code, callback, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (custom_hash, created_at, data['token'], str(data['price']), data['code'], callback_url, 'pending'))
    conn.commit()
    payment_id = cur.lastrowid
    conn.close()

    return {"url": f"/pay/{custom_hash}", "id": payment_id}, 200

#
# --- No changes needed for the routes below this line ---
# The logic fixes the URL before it's saved to the database, so
# pay(), verify_payment(), etc., will all work correctly.
#

@app.route('/pay/<custom_hash>', methods=['GET', 'POST'])
def pay(custom_hash):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, created_at, status, price, callback FROM payments WHERE custom_hash = ?', (custom_hash,))
    row = cur.fetchone()

    if not row:
        abort(404)

    payment_id, created_at_str, status, price, callback_url = row
    
    if status != 'pending':
        return f"This payment has already been completed with status: {status}.", 200

    created_at = datetime.fromisoformat(created_at_str)
    now = datetime.utcnow()
    expiry = created_at + timedelta(minutes=10)
    time_left = max(0, int((expiry - now).total_seconds()))

    if time_left == 0:
        cur.execute('UPDATE payments SET status = ? WHERE custom_hash = ?', ('declined', custom_hash))
        conn.commit()
        full_redirect_url = f"{callback_url}?hash={custom_hash}&id={payment_id}&status=0"
        conn.close()
        return redirect(full_redirect_url)

    if request.method == 'POST':
        data = request.json
        action = data.get('action')

        if action == 'accept':
            card_number = data.get('card_number', '').strip()
            cur.execute('UPDATE payments SET status = ?, card_number = ? WHERE custom_hash = ?', ('accepted', card_number, custom_hash))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": "Payment accepted."})

        elif action == 'decline':
            cur.execute('UPDATE payments SET status = ? WHERE custom_hash = ?', ('declined', custom_hash))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": "Payment declined."})
        else:
            conn.close()
            return jsonify({"status": "error", "message": "Invalid action."}), 400

    conn.close()

    try:
        formatted_price = f"{int(float(price)):,}"
        persian_map = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
        formatted_price_persian = formatted_price.translate(persian_map)
    except (ValueError, TypeError):
        formatted_price_persian = price

    return render_template('pay.html',
                           custom_hash=custom_hash,
                           payment_id=payment_id,
                           callback_url=callback_url,
                           formatted_price=formatted_price_persian,
                           time_left=time_left)


@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    data = request.form or request.json
    custom_hash = data.get('hash')
    payment_id = data.get('id')

    if not custom_hash or not payment_id:
        return {"error": "Missing hash or id"}, 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, status FROM payments WHERE id = ? AND custom_hash = ?', (payment_id, custom_hash))
    result = cur.fetchone()
    conn.close()

    if not result:
        return {"error": "Not found"}, 404

    return jsonify({"status": result[1], "id": result[0], "hash": custom_hash}), 200


if __name__ == '__main__':
    if not os.path.exists(DB_FILE):
        init_db()
    app.run(host='0.0.0.0', port=8080, debug=True)