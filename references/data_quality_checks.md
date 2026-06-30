# Data Quality Checks

Before interpreting results, check:

- Required fields: date, security code or name, direction, price, quantity.
- Amount integrity: if trade amount is missing, use `price * quantity` and mark as derived.
- Fee integrity: if commission, stamp tax, transfer fee, or other fees are missing, total fee may be understated.
- Cash balance: if missing, position sizing and capital-risk ratios are approximate or `无法判断`.
- Side balance: if there are buys but no sells, realized profit and win rate are mostly `无法判断`.
- Date integrity: invalid dates, future dates, or unsorted dates reduce confidence.
- Duplicate rows: exact duplicates can inflate turnover and trade frequency.
- Partial history: if imported data starts after existing positions were opened, average cost, holding days, and realized PnL may be inaccurate.
- Corporate actions: splits, dividends, rights issues, and transfers may break cost calculations unless included in the statement.
- External market data: without historical market prices,追高 and stop-loss simulations can only use the user's executed prices.

When a check fails, keep the analysis but clearly label affected conclusions as approximate or `无法判断`.
