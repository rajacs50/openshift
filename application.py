import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd, portfolio, tot, transaction

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure database connection
engine = create_engine("postgres://drmddgon:nUUx80PXWwPZ_MH_aZWtBo9kQk4pcGbf@satao.db.elephantsql.com:5432/drmddgon")
db = scoped_session(sessionmaker(bind=engine))

# Make sure API key is set
# if not os.environ.get("API_KEY"):
#     raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query the DB for symbol, company name, num of share, for the given user
    hs = db.execute("""WITH bought_shares AS (
                            SELECT cuid, ticker, SUM(num_shares) AS num_bought_shares
                            FROM transaction
                            WHERE cuid=:cuid AND trans_detail='by'
                            GROUP BY cuid, ticker
                            ORDER BY ticker),
                            
                            sold_shares AS (
                                SELECT cuid, ticker, SUM(num_shares) AS num_sold_shares
                                FROM transaction
                                WHERE cuid=:cuid AND trans_detail='sl'
                                GROUP BY cuid, ticker
                                ORDER BY ticker)
                                
                            SELECT t.ticker, t.company,
                                CASE
                                    WHEN b.num_bought_shares - s.num_sold_shares IS NULL THEN b.num_bought_shares
                                    ELSE b.num_bought_shares - s.num_sold_shares
                                END AS num_curr_shares
                            FROM transaction t
                            LEFT JOIN bought_shares b ON t.cuid=b.cuid AND t.ticker=b.ticker
                            LEFT JOIN sold_shares s ON t.cuid=s.cuid AND t.ticker=s.ticker
                            GROUP BY t.ticker, t.company, num_curr_shares
                            ORDER BY t.ticker""", cuid=session['user_id']).fetchall()
    # the query returns list of tuples, convert them to dict objects using list comprehension
    # need to declare variables so the dict func can iterate over and create a list of dicts
    keys = ("ticker", "company", "num_shares")
    hold_share = [dict(zip(keys, values)) for values in hs]
    # Call the helper func on the list returned by the above function
    folio = portfolio(hold_share)
    # Call the helper func for the total value based on current share val
    total = float(tot())
    # Query for getting the current user cash bal and then change the dict in the list to float
    cd = db.execute("SELECT cash FROM users WHERE id=:cuid", cuid=session['user_id'])
    cash_dict = [dict(row) for row in cd.fetchall()]
    avail_bal = float(cash_dict[0]['cash'])
    # Grand total is comprised of the avail bal, and the current holding share val
    grand_total = total + avail_bal

    return render_template("index.html", folio=folio, grand_total=usd(grand_total), avail_bal=usd(avail_bal))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via GET display the buy page
    if request.method == "GET":
        return render_template("buy.html")
    # Otherwise reached through POST (as by submitting a form via POST)
    else:
        # check if the ticker is valid and return apology if not
        if not request.form.get("symbol"):
            return apology("Missing Symbol", 400)

        # Ensure a positive integer for number of shares was submitted
        elif not request.form.get("shares"):
            return apology("Missing Shares", 400)

        else:
            # Pass the user inputted str to lookup helper func
            ticker = lookup(request.form.get("symbol"))
            # If  the response is empty, return apology
            if ticker is None:
                return apology("invalid symbol", 400)
            else:
                # if valid check how much cash the user has and how much the user selected shares cost
                # query user's available balance
                uid = dict(cuid=session['user_id'])
                cd = db.execute("SELECT cash FROM users WHERE id=:cuid", uid)
                cash_list = [d['cash'] for d in cd]
                avail_bal = int(cash_list[0])
                # the return of price from the lookup above will be in dict, separate the price
                sel_share_val = ticker["price"]
                # get the number of shares from user input
                num_shares = int(request.form.get("shares"))
                # if user hasn't enough money to buy complete the transaction return apology
                if sel_share_val * num_shares > avail_bal:
                    return apology("You don't have enough balance!", 400)
                # Otherwise add the share to the user acc and deduct the money
                else:
                    # insert the purchase details in the db
                    sym = dict(ticker=ticker['symbol'])
                    pa = dict(price_atm=sel_share_val)
                    td = dict(trans_detail='by')
                    ns = dict(num_shares=num_shares)
                    db.execute("INSERT INTO buy ('cuid', 'ticker', 'price_atm', 'trans_detail', 'num_shares') VALUES (:cuid, :ticker, :price_atm, :trans_detail, :num_shares)", (uid["cuid"], sym["ticker"], pa["price_atm"], td["trans_detail"], ns["num_shares"]))
                    # calculate the remaining bal for user after deducting his purchase
                    bal_updt = avail_bal - (sel_share_val * num_shares)
                    # update user acc with the new bal
                    bu = dict(cash=bal_updt)
                    db.execute("UPDATE users SET cash = :cash WHERE id = :cuid", (bu["cash"], uid["cuid"]))
                    conn.commit()
                    # display confirmation message and then return to portfolio
                    flash("Transaction(s) completed Successfully!")
                    # Redirect user to home page
                    return redirect("/")

@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    return jsonify("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query the DB for symbol, num of share, curr_price, transacted time for the given user
    uid = dict(cuid=session['user_id'])
    st = db.execute("SELECT ticker, CASE WHEN trans_detail = 'by' THEN num_shares ELSE '-' || num_shares END AS num_shares, price_atm, purchase_time FROM trans where cuid=:cuid ORDER BY purchase_time", uid)
    share_trans = [dict(row) for row in st.fetchall()]
    history = transaction(share_trans)
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        rows = [dict(row) for row in db.fetchall()]
        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            print(check_password_hash(rows[0]["hash"], request.form.get("password")))
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/password", methods=["GET", "POST"])
def password():
    """Lets the user change their password"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not (request.form.get("password") and request.form.get("confirmation")):
            return apology("must provide password", 403)

        # Query database for username
        username = dict(username=request.form.get("username"))
        db.execute("SELECT * FROM users WHERE username = :username", username)
        check_username = [dict(row) for row in db.fetchall()]

        # Check if username exists in the DB
        if len(check_username) == 0:
            flash("Sorry, username does not exist!")
            return render_template("password.html")

        else:
            # Hash the password and update the table
            h_pass = generate_password_hash(request.form.get("password"))
            hp = dict(hashed_pass=h_pass)
            db.execute("UPDATE users SET 'hash'=:hashed_pass", hp)
            conn.commit()
            return redirect("/")

    else:
        return render_template("password.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via GET
    if request.method == "GET":
        return render_template("quote.html")

    # User reached route via POST
    else:
        # Pass the user inputted str to lookup helper func
        ticker = lookup(request.form.get("symbol"))
        # If  the response is empty, return apology
        if ticker is None:
            return apology("invalid symbol", 400)
        # Otherwise, return the dict from lookup to quoted
        else:
            return render_template("quoted.html", ticker=ticker)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not (request.form.get("password") and request.form.get("confirmation")):
            return apology("must provide password", 403)

        # Query database for username
        check_username = db.execute("SELECT username FROM users WHERE username = :username", username=request.form.get("username")).fetchall()

        # Ensure username does not exist in the DB
        if len(check_username) > 0:
            flash("Sorry, username is already taken!")
            return render_template("register.html")

        else:
            # Add username, hash the password and add it to the DB
            hashed_pass = generate_password_hash(request.form.get("password"))
            db.execute("INSERT INTO users ('username', 'hash') VALUES (:username, :hashed_pass)", username=request.form.get("username"), hashed_pass=hashed_pass)
            flash("Registration Successfull!")
            session["user_id"] = db.lastrowid
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Query the user inputted str to check if user has that in holding
    uid = dict(cuid=session['user_id'])
    db.execute("SELECT b.ticker, IFNULL((b.num_shares-s.num_shares),b.num_shares) AS num_shares FROM buy b LEFT JOIN sell s ON b.cuid=s.cuid AND b.ticker=s.ticker where b.cuid=:cuid GROUP BY b.ticker ORDER BY b.ticker", uid)
    own_share = db.fetchall()
    # SET comprehension to get the unique ticker names
    share_avail = {l['ticker'] for l in own_share}
    # User reached route via GET display the sell page
    if request.method == "GET":
        return render_template("sell.html", share_avail=share_avail)
    # Otherwise reached through POST (as by submitting a form via POST)
    else:
        # check if the ticker is valid and return apology if not
        if not request.form.get("symbol"):
            return apology("Missing Symbol", 400)

        # Ensure a positive integer for number of shares was submitted
        elif not request.form.get("shares"):
            return apology("Missing Shares", 400)
        # Ensure that the ticker name is available in the shares owned by the user
        elif request.form.get("symbol") not in share_avail:
            return apology("You don't own this share!", 400)

        else:
            for share in own_share:
                if share['ticker'] == request.form.get("symbol"):
                    if share['num_shares'] < int(request.form.get("shares")):
                        return apology("Too many Shares", 400)
                    else:
                        # since the return of price will be in dict, separate the price
                        price = lookup(request.form.get("symbol"))
                        sel_share_val = price['price']
                        # get the number of shares from user input
                        num_shares = int(request.form.get("shares"))
                        # insert the sold details in the db
                        sym = dict(ticker=request.form.get("symbol"))
                        pa = dict(price_atm=sel_share_val)
                        td = dict(trans_detail='sl')
                        ns = dict(num_shares=num_shares)
                        db.execute("INSERT INTO sell ('cuid', 'ticker', 'price_atm', 'trans_detail', 'num_shares') VALUES (:cuid, :ticker, :price_atm, :trans_detail, :num_shares)", (uid["cuid"], sym["ticker"], pa["price_atm"], td["trans_detail"], ns["num_shares"]))
                        # Query for getting the current user cash bal and then change the dict in the list to float
                        cd = db.execute("SELECT cash FROM users WHERE id=:cuid", uid)
                        cash_dict = [dict(row) for row in cd.fetchall()]
                        avail_bal = float(cash_dict[0]['cash'])
                        # calculate the remaining bal for user after deducting his purchase
                        bal_updt = avail_bal + (sel_share_val * num_shares)
                        # update user acc with the new bal
                        bu = dict(cash=bal_updt)
                        db.execute("UPDATE users SET cash = :cash WHERE id = :cuid", (bu["cash"], uid["cuid"]))
                        conn.commit()
                        # display confirmation message and then return to portfolio
                        flash("Transaction(s) completed Successfully!")
                        # Redirect user to home page
                        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
