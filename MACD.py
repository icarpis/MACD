import pandas as pd
import yfinance as yf
import numpy as np
import pytz
from datetime import datetime as dt
import sys
import io
import plotly.graph_objs as go
import datetime



def print_signals(buy_signals, sell_signals, local_max_list):
    buy_signals = buy_signals.reset_index()[["Date", "Close"]]
    sell_signals = sell_signals.reset_index()[["Date", "Close"]]
    buy_signals["Signal Type"] = "Buy"
    sell_signals["Signal Type"] = "Sell"

    signals = pd.concat([buy_signals, sell_signals]).sort_values(by="Date").reset_index(drop=True)

    # print buy signals
    idx = 1
    print("<br><br>Signals:<br>")
    last_buy = 0
    i = 0
    for index, row in signals.iterrows():
        txt = ""
        if (row["Signal Type"] == "Buy"):
            last_buy = row['Close']
            print(str(idx) + ". Buy Signal: ")
        else:
            if (last_buy == 0):
                print(str(idx) + ". Sell Signal: ")
            else:
                print(" ; Sell Signal: ")
                
            idx+=1
            if (last_buy != 0):
                diff = float(row['Close']) - float(last_buy)
                diff_perc = "{:.4f}".format(100*((diff) / float(last_buy))) + " %)"

                color = "red"
                if (diff > 0):
                    color = "green"
                    diff_perc = " (+" + diff_perc
                else:
                    diff_perc = " (" + diff_perc
                
                txt = " ; local_max: " + "{:.2f}".format(local_max_list[i]) + " ; <p style=\"display:inline;color:" + color + ";\">Diff: " + "{:.2f}".format(diff) + diff_perc + "</p><br>"
                i+=1
            else:
                txt = "<br>"

        print("{} - {:.2f}".format(row['Date'].strftime('%Y-%m-%d'), row['Close']))
        print(txt)


# Calculate MACD indicator
def MACD(df, a, b, c):
    df["EMA_12"] = df["Close"].ewm(span=a, adjust=False).mean()
    df["EMA_26"] = df["Close"].ewm(span=b, adjust=False).mean()
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["Signal"] = df["MACD"].ewm(span=c, adjust=False).mean()
    df["Histogram"] = df["MACD"] - df["Signal"]

    # Buy and sell signals
    df["Buy"] = (df["MACD"] > df["Signal"]) & (df["MACD"].shift() < df["Signal"].shift())
    df["Sell"] = (df["MACD"] < df["Signal"]) & (df["MACD"].shift() > df["Signal"].shift())


    exp1 = df['Close'].ewm(span=a, adjust=False).mean()
    exp2 = df['Close'].ewm(span=b, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=c, adjust=False).mean()
    hist = macd - signal

    return (df, macd, signal, hist)

def handle_stock(stock_list):
    # Create figure
    fig = go.Figure()
    
    for STOCK_NAME in stock_list:
        print("Stock Name: " + STOCK_NAME + "<br>")
        stock_ticker = STOCK_NAME
        
        START_DATE = sys.argv[2].split("-")
        START_YEAR = int(START_DATE[0])
        START_MONTH = int(START_DATE[1])
        START_DAY = int(START_DATE[2])
        
        END_DATE = sys.argv[3].split("-")
        END_YEAR = int(END_DATE[0])
        END_MONTH = int(END_DATE[1])
        END_DAY = int(END_DATE[2])

        INVEST_PERCENTAGE = 100
        if (len(sys.argv) >= 6):
            INVEST_PERCENTAGE = int(sys.argv[5])
        
        
        MOVING_STOP_LOSS = int(sys.argv[6])
        
        tz = pytz.timezone("Israel")
        start_date = tz.localize(dt(START_YEAR,START_MONTH, START_DAY))
        end_date = tz.localize(dt(END_YEAR,END_MONTH, END_DAY) + datetime.timedelta(days=1))
        from dateutil.relativedelta import relativedelta
        stock_data = yf.download(stock_ticker, start=start_date - relativedelta(years=1), end=end_date)

        (df, macd, signal, hist) = MACD(stock_data, 12, 26, 9)

        df["ActualDate"] = df.index
        df = df.loc[(df['ActualDate'] >= np.datetime64(start_date)) & (df['ActualDate'] <= np.datetime64(end_date))]

        # Add trace for stock price
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=STOCK_NAME + " Stock Price"))

        # Add trace for MACD
        fig.add_trace(go.Scatter(x=df.index, y=macd, name=STOCK_NAME + " MACD"))

        # Add trace for signal
        fig.add_trace(go.Scatter(x=df.index, y=signal, name=STOCK_NAME + " Signal"))

        # Add trace for histogram
        fig.add_trace(go.Bar(x=df.index, y=hist, name=STOCK_NAME + " Histogram"))

        # Add buy and sell signals
        buy_signals = df[(macd > signal) & (macd.shift() < signal.shift())]
        sell_signals = df[(macd < signal) & (macd.shift() > signal.shift())]

        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals["Close"], mode="markers", marker=dict(symbol="triangle-up", size=10, color="green"), name=STOCK_NAME + " Buy"))
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals["Close"], mode="markers", marker=dict(symbol="triangle-down", size=10, color="red"), name=STOCK_NAME + " Sell"))


        dates_list = []
        cash_list = []
        first_investment = 100
        cash_list.append(first_investment)
        dates_list.append(df["ActualDate"][0])


        last_sell_cash = None
        success_rate = 0
        num_of_sells = 0


        cash = first_investment  # start with first_investment in cash
        shares = 0
        
        stop_loss_buy_cash = first_investment  # start with first_investment in cash
        stop_loss_buy_shares = 0

        static_cash = cash - ((cash * INVEST_PERCENTAGE)/100)
        static_shares = static_cash / stock_data["Close"][0]

        buy_amount = ((cash * INVEST_PERCENTAGE)/100)
        local_max = 0
        local_max_list = []
        after_buy = False
        moving_stop_loss_list = []
        moving_stop_loss_dates = []
        sell_idx = 0
        after_moving_stop_loss = False
        for i in range(len(df)):
            if (df["Close"][i] > local_max):
                local_max = df["Close"][i]

            if df["Buy"][i] == True:
                shares_to_buy = buy_amount / df["Close"][i]  # calculate number of shares to buy
                
                shares += shares_to_buy  # add shares to portfolio
                cash -= buy_amount
                
                stop_loss_buy_shares += shares_to_buy
                stop_loss_buy_cash -= buy_amount
                
                
                local_max = df["Close"][i]
                after_buy = True
            elif (df["Sell"][i] == True):
                cash_from_sale = shares * df["Close"][i]  # calculate cash from selling shares
                
                shares = 0
                cash += cash_from_sale
                
                if (not after_moving_stop_loss):
                    stop_loss_buy_shares = 0
                    stop_loss_buy_cash += cash_from_sale
                    
                after_moving_stop_loss = False
            
                cash_list.append(cash)
                dates_list.append(df["ActualDate"][i])
                
                local_max_list.append(local_max)
                local_max = 0
                if (not after_buy) and (sell_idx == 0):
                    sell_idx += 2
                else:
                    sell_idx += 1
                
                after_buy = False
                
                num_of_sells+=1
                if (last_sell_cash != None):
                    if (cash_from_sale > last_sell_cash):
                        success_rate+=1

                last_sell_cash = cash_from_sale
                
            elif (after_buy and (local_max != 0) and (MOVING_STOP_LOSS != 0) and ((((local_max - df["Close"][i])/local_max) * 100) >= MOVING_STOP_LOSS)):
                moving_stop_loss_list.append(df["Close"][i])
                moving_stop_loss_dates.append(df["ActualDate"][i])
                #sell_signals["Close"][sell_idx] = df["Close"][i]
                after_buy = False
                
                #print(str(df["ActualDate"][i]) + "  " + str(df["Close"][i]))
                
                cash_from_sale = stop_loss_buy_shares * df["Close"][i]  # calculate cash from selling shares
                
                stop_loss_buy_shares = 0
                stop_loss_buy_cash += cash_from_sale
               
                after_moving_stop_loss = True


        fig.add_trace(go.Scatter(x=moving_stop_loss_dates, y=moving_stop_loss_list, mode="markers", marker=dict(symbol="triangle-down", size=10, color="brown"), name=STOCK_NAME + " Moving Stop-Loss"))

        if (static_cash != 0):
            cash -= static_cash
            cash += (static_shares * stock_data["Close"][-1])
            cash_list.append(cash)


        print_signals(buy_signals, sell_signals, local_max_list)

        # Calculate final investment value
        final_investment = cash + shares * df["Close"][-1]

        # Calculate profit
        profit = final_investment - first_investment

        stop_loss_buy_final_investment = stop_loss_buy_cash + stop_loss_buy_shares * df["Close"][-1]
        
        stop_loss_buy_profit = stop_loss_buy_final_investment - first_investment


        print("<br><br><br>Stock Name: " + STOCK_NAME + "<br>")
        # Print final investment value and profit
        print("Start Date: " + sys.argv[2])
        print("<br>End Date: " + sys.argv[3])
        
        print("<br><br>Cash Investment Precentage on Buy Signal: {}%<br>".format(INVEST_PERCENTAGE))
        
        print("<br>MACD Profit: {:.2f} %<br>".format(profit))
        
        if (MOVING_STOP_LOSS != 0):
            print("<br>MACD Stop-Loss Profit: {:.2f} %<br>".format(stop_loss_buy_profit))

        first_investment_shares = first_investment / df["Close"][0]
        passive_investment_profit = first_investment_shares * df["Close"][-1] - first_investment
        print("Passive Investment Profit: {:.2f} % <br>".format(passive_investment_profit))
        
        if (num_of_sells != 0):
            print("Success Rate: {:.2f} %<br><br><br>".format((success_rate/num_of_sells) * 100))
            
        fig.add_trace(go.Scatter(x=dates_list, y=cash_list, name=STOCK_NAME + " Cash"))
    return fig

def main():
    try:
        stock_list = []
        # Load stock data
        stock_list.append(sys.argv[1].upper())
        
        if (len(sys.argv) >= 5):
            if (sys.argv[4] != "-"):
                stock_list.append(sys.argv[4].upper())

        fig = handle_stock(stock_list)

        print('<br><br>' + fig.to_html(full_html=False, include_plotlyjs='cdn'))

    except Exception as er:
        print("<br><br>ERROR!!!!!!!!!!!!!!<br>")
        print(er)
    except:
        print("<br><br>ERROR!!!!!!!!!!!!!!")

if __name__ == "__main__":
    sys.exit(main())