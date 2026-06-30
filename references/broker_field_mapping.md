# Broker Field Mapping

Normalize broker exports into these canonical fields:

| Canonical field | Common aliases |
|---|---|
| `trade_date` | 成交日期, 交易日期, 发生日期, 委托日期, 日期, business_date, trade date, date |
| `security_code` | 证券代码, 股票代码, 代码, 合约代码, 证券编号, stock_code, symbol, ticker |
| `security_name` | 证券名称, 股票名称, 名称, 合约名称, stock_name, security_name |
| `side` | 买卖方向, 交易方向, 操作, 买卖标志, 业务名称, direction, side, action |
| `price` | 成交价格, 成交均价, 价格, 成交价, price, fill_price |
| `quantity` | 成交数量, 成交股数, 数量, 股数, 成交量, quantity, qty, shares |
| `trade_amount` | 成交金额, 发生金额, 成交额, 委托金额, amount, gross_amount, turnover |
| `commission` | 手续费, 佣金, 交易佣金, commission, fee |
| `stamp_tax` | 印花税, stamp_tax |
| `transfer_fee` | 过户费, transfer_fee |
| `other_fee` | 其他费用, 规费, 经手费, 证管费, 结算费, other_fee |
| `cash_amount` | 发生金额, 清算金额, 资金发生额, 资金变动, net_amount, cash_amount |
| `cash_balance` | 资金余额, 可用余额, 余额, 资金结余, cash_balance, balance |

Direction normalization:

- Buy: 买入, 证券买入, 买, B, BUY, purchase
- Sell: 卖出, 证券卖出, 卖, S, SELL, redemption

If both `成交金额` and `发生金额` exist, treat `成交金额` as gross trade amount and `发生金额` as signed cash movement.
