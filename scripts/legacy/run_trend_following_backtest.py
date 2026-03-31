#!/usr/bin/env python
"""
趋势跟踪策略回测

改进点：
1. 改为趋势跟踪而非选股
2. 只做强势股（相对大盘强势）
3. 严格择时：只在上升趋势交易
4. 快速止损，让利润奔跑
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_db_config():
    """加载数据库配置"""
    config_path = os.path.join(os.path.dirname(__file__), '.vntrader', 'vt_setting.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        return {
            'host': config.get('database.host', 'localhost'),
            'port': config.get('database.port', 3306),
            'user': config.get('database.user', 'root'),
            'password': config.get('database.password', ''),
            'database': config.get('database.database', 'stock'),
        }
    return None


class TrendFollowingBacktest:
    """趋势跟踪策略回测"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.db = None
        self._init_database()
        
        # 策略参数
        self.params = {
            'trend_lookback': 20,      # 趋势判断周期
            'momentum_period': 60,     # 动量计算周期
            'stop_loss': 0.05,         # 止损 5%
            'trailing_stop': 0.10,     # 跟踪止损 10%
            'max_positions': 5,        # 最大持仓数
            'position_size': 0.15,     # 单股仓位 15%
            'min_momentum': 0.05,      # 最小动量 5%
            'market_filter': True,     # 大盘过滤
        }
        
    def _init_database(self):
        """初始化数据库连接"""
        try:
            from vnpy.trader.setting import SETTINGS
            SETTINGS["database.database"] = self.db_config['database']
            SETTINGS["database.user"] = self.db_config['user']
            SETTINGS["database.password"] = self.db_config['password']
            SETTINGS["database.host"] = self.db_config['host']
            SETTINGS["database.port"] = self.db_config['port']
            
            from vnpy_mysql import Database
            self.db = Database()
            print("✓ 数据库连接成功")
        except Exception as e:
            print(f"✗ 数据库连接失败: {e}")
            self.db = None
    
    def get_stock_data(self, vt_symbol: str, start_date: str, end_date: str) -> Optional[Dict]:
        """获取单只股票数据"""
        if not self.db:
            return None
        
        try:
            parts = vt_symbol.split('.')
            if len(parts) != 2:
                return None
            
            symbol = parts[0]
            exchange_str = parts[1]
            
            from vnpy.trader.object import Interval
            from vnpy.trader.constant import Exchange
            
            exchange_map = {
                'SZSE': Exchange.SZSE,
                'SSE': Exchange.SSE,
            }
            ex = exchange_map.get(exchange_str, Exchange.SSE)
            
            bars = self.db.load_bar_data(
                symbol=symbol,
                exchange=ex,
                interval=Interval.DAILY,
                start=datetime.strptime(start_date, '%Y-%m-%d'),
                end=datetime.strptime(end_date, '%Y-%m-%d')
            )
            
            if not bars or len(bars) < self.params['momentum_period']:
                return None
            
            data = {
                'dates': [],
                'close': [],
                'high': [],
                'low': [],
                'volume': [],
            }
            
            for bar in bars:
                data['dates'].append(bar.datetime)
                data['close'].append(bar.close_price)
                data['high'].append(bar.high_price)
                data['low'].append(bar.low_price)
                data['volume'].append(bar.volume)
            
            return data
            
        except Exception as e:
            return None
    
    def calculate_momentum(self, prices: List[float], period: int) -> float:
        """计算价格动量"""
        if len(prices) < period:
            return 0
        
        current = prices[-1]
        past = prices[-period]
        
        if past == 0:
            return 0
        
        return (current - past) / past
    
    def calculate_trend_score(self, prices: List[float]) -> float:
        """
        计算趋势得分
        综合多周期趋势
        """
        if len(prices) < 60:
            return 0
        
        # 多周期动量
        mom_20 = self.calculate_momentum(prices, 20)
        mom_40 = self.calculate_momentum(prices, 40)
        mom_60 = self.calculate_momentum(prices, 60)
        
        # 加权平均
        trend_score = 0.5 * mom_20 + 0.3 * mom_40 + 0.2 * mom_60
        
        return trend_score
    
    def check_trend_alignment(self, prices: List[float]) -> bool:
        """
        检查趋势是否一致向上
        短期 > 中期 > 长期
        """
        if len(prices) < 60:
            return False
        
        # 计算均线
        ma10 = sum(prices[-10:]) / 10
        ma20 = sum(prices[-20:]) / 20
        ma60 = sum(prices[-60:]) / 60
        
        # 多头排列
        return ma10 > ma20 > ma60
    
    def run_backtest(self,
                    start_date: str = "2022-01-01",
                    end_date: str = "2024-01-01",
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 100) -> Dict:
        """运行回测"""
        
        print("\n" + "="*60)
        print("趋势跟踪策略回测")
        print("="*60)
        
        if not self.db:
            print("✗ 数据库未连接")
            return {}
        
        # 获取股票列表
        print("\n获取股票列表...")
        try:
            from vnpy_mysql.mysql_database import DbBarData
            query = (DbBarData
                    .select(DbBarData.symbol, DbBarData.exchange)
                    .distinct()
                    .where(DbBarData.interval == 'd'))
            
            all_stocks = []
            seen = set()
            for row in query:
                vt_symbol = f"{row.symbol}.{row.exchange}"
                if vt_symbol not in seen:
                    all_stocks.append(vt_symbol)
                    seen.add(vt_symbol)
            
            print(f"✓ 获取到 {len(all_stocks)} 只股票")
            
            if len(all_stocks) > max_stocks:
                all_stocks = all_stocks[:max_stocks]
        except Exception as e:
            print(f"✗ 获取股票列表失败: {e}")
            return {}
        
        # 加载股票数据
        print(f"\n加载股票数据...")
        stock_data = {}
        
        for i, vt_symbol in enumerate(all_stocks):
            if i % 20 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            data = self.get_stock_data(vt_symbol, start_date, end_date)
            
            if data and len(data['close']) >= self.params['momentum_period']:
                stock_data[vt_symbol] = data
        
        print(f"✓ 成功加载 {len(stock_data)} 只股票的数据")
        
        if len(stock_data) < 10:
            print("✗ 可用股票数量不足")
            return {}
        
        # 运行回测
        return self._simulate_trading(stock_data, start_date, end_date, initial_capital)
    
    def _simulate_trading(self, stock_data: Dict,
                         start_date: str, end_date: str,
                         initial_capital: float) -> Dict:
        """模拟交易"""
        
        first_stock = list(stock_data.values())[0]
        trading_days = len(first_stock['dates'])
        
        print(f"\n回测参数:")
        print(f"  交易日数: {trading_days}")
        print(f"  趋势周期: {self.params['trend_lookback']}")
        print(f"  动量周期: {self.params['momentum_period']}")
        print(f"  止损: {self.params['stop_loss']*100:.0f}%")
        print(f"  跟踪止损: {self.params['trailing_stop']*100:.0f}%")
        print(f"  最大持仓: {self.params['max_positions']}")
        
        print("\n模拟交易...")
        
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        # 持仓管理
        positions = {}  # {vt_symbol: {'entry_price': float, 'shares': int, 'max_price': float}}
        cash = initial_capital
        
        for day in range(self.params['momentum_period'], trading_days):
            # 对每只股票计算趋势得分
            stock_scores = []
            
            for vt_symbol, data in stock_data.items():
                if day >= len(data['close']):
                    continue
                
                hist_close = data['close'][:day]
                
                # 计算趋势得分
                trend_score = self.calculate_trend_score(hist_close)
                
                # 检查趋势一致性
                trend_aligned = self.check_trend_alignment(hist_close)
                
                # 只选择强势且趋势一致的股票
                if trend_score > self.params['min_momentum'] and trend_aligned:
                    stock_scores.append((vt_symbol, trend_score, data))
            
            # 排序并选择前N只
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            selected = stock_scores[:self.params['max_positions']]
            selected_symbols = {s[0] for s in selected}
            
            # 检查止损止盈和调仓
            for vt_symbol in list(positions.keys()):
                if vt_symbol not in stock_data:
                    continue
                
                data = stock_data[vt_symbol]
                if day >= len(data['close']):
                    continue
                
                current_price = data['close'][day]
                pos = positions[vt_symbol]
                
                # 更新最高价
                if current_price > pos['max_price']:
                    pos['max_price'] = current_price
                
                # 计算盈亏
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                # 止损
                if pnl_pct <= -self.params['stop_loss']:
                    cash += pos['shares'] * current_price
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'stop_loss', 'day': day, 'pnl': pnl_pct})
                    continue
                
                # 跟踪止损
                max_pnl = (pos['max_price'] - pos['entry_price']) / pos['entry_price']
                if max_pnl > 0.05:  # 盈利超过5%后启用跟踪止损
                    trailing_pnl = (current_price - pos['max_price']) / pos['max_price']
                    if trailing_pnl <= -self.params['trailing_stop']:
                        cash += pos['shares'] * current_price
                        del positions[vt_symbol]
                        trades.append({'symbol': vt_symbol, 'action': 'trailing_stop', 'day': day, 'pnl': pnl_pct})
                        continue
                
                # 如果不在选股列表中，卖出
                if vt_symbol not in selected_symbols:
                    cash += pos['shares'] * current_price
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'sell', 'day': day, 'pnl': pnl_pct})
            
            # 计算当前仓位价值
            position_value = sum(
                positions[vt_symbol]['shares'] * stock_data[vt_symbol]['close'][day]
                for vt_symbol in positions
                if vt_symbol in stock_data and day < len(stock_data[vt_symbol]['close'])
            )
            
            total_value = cash + position_value
            
            # 买入新选中的股票
            target_position_value = total_value * self.params['position_size']
            
            for vt_symbol, score, data in selected:
                if vt_symbol in positions:
                    continue
                
                # 检查是否超过最大持仓数
                if len(positions) >= self.params['max_positions']:
                    break
                
                # 检查是否有足够现金
                current_price = data['close'][day]
                shares = int(target_position_value / current_price)
                
                if shares > 0 and cash >= shares * current_price:
                    positions[vt_symbol] = {
                        'entry_price': current_price,
                        'shares': shares,
                        'max_price': current_price
                    }
                    cash -= shares * current_price
                    trades.append({
                        'symbol': vt_symbol,
                        'action': 'buy',
                        'day': day,
                        'score': score,
                        'price': current_price,
                        'shares': shares
                    })
            
            # 计算当日总资产
            position_value = sum(
                positions[vt_symbol]['shares'] * stock_data[vt_symbol]['close'][day]
                for vt_symbol in positions
                if vt_symbol in stock_data and day < len(stock_data[vt_symbol]['close'])
            )
            
            total_value = cash + position_value
            portfolio_value = total_value
            
            # 计算日收益率
            if len(portfolio_values) > 0:
                daily_return = (portfolio_value - portfolio_values[-1]) / portfolio_values[-1]
            else:
                daily_return = 0
            
            portfolio_values.append(portfolio_value)
            daily_returns.append(daily_return)
        
        # 计算绩效指标
        return self._calculate_performance(
            portfolio_values, daily_returns, trades,
            start_date, end_date, initial_capital
        )
    
    def _calculate_performance(self, portfolio_values: List[float],
                              daily_returns: List[float],
                              trades: List[Dict],
                              start_date: str, end_date: str,
                              initial_capital: float) -> Dict:
        """计算绩效指标"""
        
        def mean(data):
            return sum(data) / len(data) if data else 0
        
        def std(data):
            if len(data) < 2:
                return 0
            avg = mean(data)
            variance = sum((x - avg) ** 2 for x in data) / (len(data) - 1)
            return math.sqrt(variance)
        
        total_return = (portfolio_values[-1] - initial_capital) / initial_capital
        trading_days = len(daily_returns)
        years = trading_days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 夏普比率
        risk_free_rate = 0.03
        if std(daily_returns) > 0:
            sharpe_ratio = math.sqrt(252) * (mean(daily_returns) - risk_free_rate/252) / std(daily_returns)
        else:
            sharpe_ratio = 0
        
        # 最大回撤
        cumulative = [v / initial_capital for v in portfolio_values]
        running_max = [max(cumulative[:i+1]) for i in range(len(cumulative))]
        drawdown = [(c - rm) / rm for c, rm in zip(cumulative, running_max)]
        max_drawdown = min(drawdown) if drawdown else 0
        
        # 回撤持续期
        max_dd_duration = 0
        current_dd_duration = 0
        for dd in drawdown:
            if dd < -0.001:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0
        
        volatility = std(daily_returns) * math.sqrt(252)
        win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns) if daily_returns else 0
        
        # 计算交易胜率
        trade_profits = [t for t in trades if t.get('pnl', 0) > 0]
        trade_losses = [t for t in trades if t.get('pnl', 0) <= 0]
        trade_win_rate = len(trade_profits) / len(trades) if trades else 0
        
        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "max_drawdown_duration": int(max_dd_duration),
            "volatility": float(volatility),
            "total_trades": len(trades),
            "win_rate": float(win_rate),
            "trade_win_rate": float(trade_win_rate),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": float(initial_capital),
            "final_capital": float(portfolio_values[-1]),
            "trading_days": trading_days,
            "params": self.params,
        }


def print_result(result: Dict):
    """打印回测结果"""
    print("\n" + "="*60)
    print("趋势跟踪策略回测绩效报告")
    print("="*60)
    print(f"回测区间: {result.get('start_date', 'N/A')} ~ {result.get('end_date', 'N/A')}")
    print(f"交易天数: {result.get('trading_days', 0)}")
    print(f"初始资金: {result.get('initial_capital', 0):,.2f}")
    print(f"最终资金: {result.get('final_capital', 0):,.2f}")
    print("-"*60)
    print("【收益指标】")
    print(f"  总收益率:    {result.get('total_return', 0)*100:>10.2f}%")
    print(f"  年化收益率:  {result.get('annual_return', 0)*100:>10.2f}%")
    print(f"  夏普比率:    {result.get('sharpe_ratio', 0):>10.4f}")
    print("-"*60)
    print("【风险指标】")
    print(f"  最大回撤:    {result.get('max_drawdown', 0)*100:>10.2f}%")
    print(f"  回撤持续:    {result.get('max_drawdown_duration', 0):>10}天")
    print(f"  年化波动率:  {result.get('volatility', 0)*100:>10.2f}%")
    print("-"*60)
    print("【交易指标】")
    print(f"  总交易次数:  {result.get('total_trades', 0):>10}")
    print(f"  日胜率:      {result.get('win_rate', 0)*100:>10.2f}%")
    print(f"  交易胜率:    {result.get('trade_win_rate', 0)*100:>10.2f}%")
    print("="*60)
    
    sharpe = result.get('sharpe_ratio', 0)
    if sharpe >= 1.0:
        print(f"✓ 夏普率达到目标: {sharpe:.4f} >= 1.0")
    else:
        print(f"✗ 夏普率未达标: {sharpe:.4f} < 1.0")
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股趋势跟踪策略回测")
    print("="*60)
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    print(f"\n数据库配置:")
    print(f"  主机: {db_config['host']}")
    print(f"  端口: {db_config['port']}")
    print(f"  数据库: {db_config['database']}")
    
    backtest = TrendFollowingBacktest(db_config)
    
    if not backtest.db:
        print("\n✗ 数据库连接失败")
        return
    
    result = backtest.run_backtest(
        start_date="2022-01-01",
        end_date="2024-01-01",
        initial_capital=1000000.0,
        max_stocks=100
    )
    
    if result:
        print_result(result)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"trend_following_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
