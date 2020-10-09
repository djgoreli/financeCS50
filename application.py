from __future__ import print_function
import sys
import os
import csv
import urllib.request

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime


from helpers import apology, login_required, lookup, usd
#export API_KEY=DXSEBJJXVOMBXZ
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
# Ensure environment variable is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

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
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    selectedStocks= db.execute("SELECT * FROM stocks WHERE userID= :id AND shares>0", id =session["user_id"])
    #print(selectedStocks)
    cash= db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id']) #returns a list of one dict with user's current in it
    cash= usd(cash[0]["cash"])


    if len(selectedStocks)>0:
        for i in range(len(selectedStocks)):
            selectedStocks[i]["total"]=usd(selectedStocks[i]["total"])
            selectedStocks[i]["price"]= usd(selectedStocks[i]["price"])

    """Show portfolio of stocks"""
    return render_template("index.html", stocks= selectedStocks, userCash= cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")
    elif request.method == "POST":
        symbol=request.form.get("symbol")
        if not symbol:
            return apology("Enter a symbol")
        if not request.form.get("shares"):
            return apology("Enter shares")
        shares=int(request.form.get("shares"))

        shareInfo=lookup(symbol)

        if not shareInfo:
            return apology("Not a valid symbol")
        if not symbol.isupper():
            return apology("Enter symbols in all uppercase")
        if not shares>0:
            return apology("Enter a symbol and a positive integer amount of shares")

        shares=int(request.form.get("shares"))
        cash= db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id']) #returns a list of one dict with user's current in it
        cash= cash[0]["cash"]
        if not shares>=0:
            return apology("Enter a symbol and a positive integer amount of shares")
        if cash<shareInfo["price"]*shares:
            return apology("Insufficient Funds")
        transaction= db.execute("INSERT INTO purchases (stock, price, shares, time, userID, type) VALUES(:stock, :price, :shares, :time, :userID, :type)",
                    stock=symbol,shares=shares, price=shares*shareInfo["price"], time=str(datetime.now()),
                    userID= session["user_id"], type= "buy")
        amountBought=db.execute("SELECT SUM(shares) FROM purchases WHERE userID=:id AND stock=:stock AND type=:type", id=session['user_id'], stock=symbol, type="buy")
        amountBought=amountBought[0]['SUM(shares)']
        amountSold=db.execute("SELECT SUM(shares) FROM purchases WHERE userID=:id AND stock=:stock AND type=:type", id=session['user_id'], stock=symbol, type="sell")
        if not amountSold[0]['SUM(shares)']:
            amountSold=0
        else:
            amountSold=amountSold[0]['SUM(shares)']

        amount=amountBought-amountSold
        if len(db.execute("SELECT shares FROM stocks WHERE userID=:id AND symbol=:stock", id=session['user_id'], stock=symbol))==0:
            stockAmounts= db.execute("INSERT INTO stocks (symbol, shares, price, total, userID) VALUES(:symbol, :shares, :price, :total, :userID)",
                                symbol=symbol, shares=amount, price=shareInfo["price"], total=amount*shareInfo["price"],
                                userID= session["user_id"]) #BUG with shares

        else:
            db.execute("UPDATE 'stocks' SET shares= :amount where userID=:id AND symbol= :symbol", amount=amount, id=session["user_id"], symbol=symbol)
            db.execute("UPDATE 'stocks' SET total= :total where userID=:id AND symbol=:symbol", total=amount*shareInfo["price"], id=session["user_id"], symbol=symbol)
        updateCash= db.execute("UPDATE 'users' SET cash= :cash where id= :id",
                    cash=cash-shareInfo["price"]*shares, id=session['user_id'])
        return redirect("/")



@app.route("/history")
@login_required
def history():
    selectedStocks= db.execute("SELECT * FROM purchases WHERE userID= :id", id =session["user_id"])
    #print(selectedStocks)
    if len(selectedStocks)>0:
        for i in range(len(selectedStocks)):
            selectedStocks[i]["price"]= usd(selectedStocks[i]["price"])

    """Show portfolio of stocks"""
    return render_template("history.html", stocks= selectedStocks)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    symbol = request.args.get("symbol")
    if not symbol:
        return render_template("quote.html")


    url = f"https://www.alphavantage.co/query?apikey=NAJXWIA8D6VN6A3K&datatype=csv&function=TIME_SERIES_INTRADAY&interval=1min&symbol={symbol}"
    webpage = urllib.request.urlopen(url)
    datareader = csv.reader(webpage.read().decode("utf-8").splitlines())
    next(datareader)
    row = next(datareader)
    return jsonify({
    	"name": symbol.upper(),
        "price": float(row[4]),
        "symbol": symbol.upper()
    })


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    elif request.method == "POST":
        if not request.form.get("username") or not request.form.get("password") or not request.form.get("reEnterPassword"):
            return apology("No username or password")
        elif not request.form.get("password")==request.form.get("reEnterPassword"):
            return apology("Make sure that password and confirmation are the same")

        sessID = db.execute("INSERT INTO users (username, hash) VALUES(:username, :password)",
                    username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))
        if not sessID:
            return apology("username has been taken")
        session["user_id"] = sessID
        return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    selectedStocks= db.execute("SELECT symbol FROM stocks WHERE userID= :id AND shares>0", id =session["user_id"])
    if request.method == "GET":
        return render_template("sell.html", stocks= selectedStocks)
    elif request.method == "POST":
        symbol=request.form.get("symbol")
        if not symbol:
            return apology("Enter a symbol")
        if not request.form.get("shares"):
            return apology("Enter shares")
        shares=int(request.form.get("shares"))

        shareInfo=lookup(symbol)

        if not shareInfo:
            return apology("Not a valid symbol")
        if not shares>0:
            return apology("Enter a symbol and a positive integer amount of shares")
        stockAmount= db.execute("SELECT shares FROM stocks WHERE userID= :id AND symbol=:symbol", id=session["user_id"], symbol=symbol)
        stockAmount= stockAmount[0]["shares"]
        cash= db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id']) #returns a list of one dict with user's current in it
        cash= cash[0]["cash"]
        if shares>stockAmount:
            return apology("You don't own enough of this stock")
        transaction= db.execute("INSERT INTO purchases (stock, price, shares, time, userID, type) VALUES(:stock, :price, :shares, :time, :userID, :type)",
                    stock=symbol,shares=shares, price=shares*shareInfo["price"], time=str(datetime.now()),
                    userID= session["user_id"], type= "sell")
        total= db.execute("SELECT total FROM stocks WHERE userID= :id AND symbol=:symbol", id=session["user_id"], symbol=symbol)
        total= total[0]["total"]
        if stockAmount==0:
            deleteStocks= db.execute("DELETE * FROM 'stocks' WHERE userID= :id AND symbol=:symbol", id=session["user_id"], symbol=symbol)
        if stockAmount>0:
            updatedStocks=db.execute("UPDATE 'stocks' SET shares= :amount where userID=:id AND symbol=:symbol", amount=stockAmount-shares, id=session["user_id"], symbol=symbol)
            updatedTotal= db.execute("UPDATE 'stocks' SET total= :total where userID=:id AND symbol=:symbol", total=total-shares*shareInfo["price"], id=session["user_id"], symbol=symbol)
            updateCash= db.execute("UPDATE 'users' SET cash= :cash where id= :id",
                    cash=cash+shareInfo["price"]*shares, id=session['user_id'])
        deleteShares= db.execute("DELETE FROM 'stocks' WHERE userID= :id AND shares=:shares", id=session["user_id"], shares=0)
        eprint(stockAmount, "HAHAHAHAH")



    return redirect("/")


# def errorhandler(e):
#    """Handle error"""
#    return apology(e.name, e.code)


# listen for errors
# for code in default_exceptions:
#    app.errorhandler(code)(errorhandler)
