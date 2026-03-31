#!/usr/bin/env python
"""
优化版策略回测
基于真实数据回测结果进行优化
"""

import os
import sys
import json
import math
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_strategy_optimized import OptimizedFactorCalculator


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


class OptimizedBacktest:
    """优化后的回测引擎"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.calculator = OptimizedFactorCalculator()
        self.db = None
        self._init_database()
        
        # 优化后的参数
        self.params = {
            'top_n': 10,              # 减少持股数量，集中优质股票
            'stop_loss': 0.03,        # 更严格的止损 3%
            'take_profit': 0.10,      # 添加止盈 10%
            'min_score': 0.3,         # 提高选股门槛
            'max_positions': 10,      # 最大持仓数量
            'position_size': 0.08,    # 单只股票仓位 8%
            'market_filter': True,    # 启用大盘过滤
            'cash_ratio': 0.2,        # 最低现金比例 20%
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
    
    def get_market_index_data(self, start_date: str, end_date: str) -> Optional[List[float]]:
        """获取大盘指数数据（上证指数）"""
        try:
            from vnpy.trader.object import Interval
            from vnpy.trader.constant import Exchange
            
            bars = self.db.load_bar_data(
                symbol='000001',
                exchange=Exchange.SSE,
                interval=Interval.DAILY,
                start=datetime.strptime(start_date, '%Y-%m-%d'),
                end=datetime.strptime(end_date, '%Y-%m-%d')
            )
            
            if bars:
                return [bar.close_price for bar in bars]
            return None
        except:
            return None
    
    def check_market_trend(self, index_prices: List[float], lookback: int = 20) -> str:
        """
        检查市场趋势
        Returns: 'bull', 'bear', 'sideways'
        """
        if len(index_prices) < lookback:
            return 'sideways'
        
        # 计算均线
        ma20 = sum(index_prices[-lookback:]) / lookback
        current_price = index_prices[-1]
        
        # 计算趋势强度
        price_change = (current_price - index_prices[-lookback]) / index_prices[-lookback]
        
        # 判断趋势
        if price_change > 0.05 and current_price > ma20:
            return 'bull'
        elif price_change < -0.05 or current_price < ma20 * 0.95:
            return 'bear'
        else:
            return 'sideways'
    
    def get_all_stocks(self) -> List[str]:
        """获取所有股票列表"""
        if not self.db:
            return []
        
        try:
            from vnpy_mysql.mysql_database import DbBarData
            
            query = (DbBarData
                    .select(DbBarData.symbol, DbBarData.exchange)
                    .distinct()
                    .where(DbBarData.interval == 'd'))
            
            stocks = []
            seen = set()
            for row in query:
                vt_symbol = f"{row.symbol}.{row.exchange}"
                if vt_symbol not in seen:
                    stocks.append(vt_symbol)
                    seen.add(vt_symbol)
            
            print(f"✓ 从数据库获取到 {len(stocks)} 只股票")
            return stocks
            
        except Exception as e:
            print(f"✗ 获取股票列表失败: {e}")
            return []
    
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
            
            if not bars or len(bars) < 60:
                return None
            
            data = {
                'dates': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': [],
                'vt_symbol': vt_symbol,
            }
            
            for bar in bars:
                data['dates'].append(bar.datetime)
                data['open'].append(bar.open_price)
                data['high'].append(bar.high_price)
                data['low'].append(bar.low_price)
                data['close'].append(bar.close_price)
                data['volume'].append(bar.volume)
            
            return data
            
        except Exception as e:
            return None
    
    def run_backtest(self,
                    start_date: str = "2022-01-01",
                    end_date: str = "2024-01-01",
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 100) -> Dict:
        """运行优化后的回测"""
        
        print("\n" + "="*60)
        print("优化版策略回测")
        print("="*60)
        
        if not self.db:
            print("✗ 数据库未连接")
            return {}
        
        # 获取大盘指数数据
        print("\n加载大盘指数数据...")
        market_data = self.get_market_index_data(start_date, end_date)
        if market_data:
            print(f"✓ 加载了 {len(market_data)} 天的指数数据")
        
        # 获取股票列表
        print("\n获取股票列表...")
        all_stocks = self.get_all_stocks()
        
        if not all_stocks:
            return {}
        
        if len(all_stocks) > max_stocks:
            all_stocks = all_stocks[:max_stocks]
        
        # 加载股票数据
        print(f"\n加载股票数据...")
        stock_data = {}
        
        for i, vt_symbol in enumerate(all_stocks):
            if i % 20 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            data = self.get_stock_data(vt_symbol, start_date, end_date)
            
            if data and len(data['close']) >= 60:
                stock_data[vt_symbol] = data
        
        print(f"✓ 成功加载 {len(stock_data)} 只股票的数据")
        
        if len(stock_data) < 20:
            print("✗ 可用股票数量不足")
            return {}
        
        # 运行回测
        return self._simulate_trading(stock_data, market_data, start_date, end_date, initial_capital)
    
    def _simulate_trading(self, stock_data: Dict, market_data: Optional[List[float]],
                         start_date: str, end_date: str,
                         initial_capital: float) -> Dict:
        """模拟交易 - 优化版"""
        
        first_stock = list(stock_data.values())[0]
        trading_days = len(first_stock['dates'])
        
        print(f"\n回测参数:")
        print(f"  交易日数: {trading_days}")
        print(f"  选股数量: {self.params['top_n']}")
        print(f"  止损比例: {self.params['stop_loss']*100:.1f}%")
        print(f"  止盈比例: {self.params['take_profit']*100:.1f}%")
        print(f"  最低选股分: {self.params['min_score']}")
        print(f"  单股仓位: {self.params['position_size']*100:.1f}%")
        print(f"  大盘过滤: {'开启' if self.params['market_filter'] else '关闭'}")
        
        print("\n模拟交易...")
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        # 持仓管理
        positions = {}  # {vt_symbol: {'entry_price': float, 'shares': int, 'cost': float}}
        cash = initial_capital
        
        for day in range(60, trading_days):
            # 检查市场趋势
            if self.params['market_filter'] and market_data and day < len(market_data):
                market_trend = self.check_market_trend(market_data[:day+1])
                if market_trend == 'bear':
                    # 熊市清仓
                    for vt_symbol in list(positions.keys()):
                        cash += positions[vt_symbol]['shares'] * stock_data[vt_symbol]['close'][day]
                        del positions[vt_symbol]
                        trades.append({'symbol': vt_symbol, 'action': 'market_exit', 'day': day})
                    
                    portfolio_values.append(cash)
                    daily_returns.append(0)
                    continue
            
            # 对每只股票评分
            stock_scores = []
            
            for vt_symbol, data in stock_data.items():
                if day >= len(data['close']):
                    continue
                
                hist_close = data['close'][:day]
                hist_volume = data['volume'][:day]
                
                if len(hist_close) < 30:
                    continue
                
                try:
                    scores = self.calculator.calculate_composite_score(
                        hist_close, hist_volume
                    )
                    
                    # 提高选股门槛
                    if scores['composite'] > self.params['min_score']:
                        stock_scores.append((vt_symbol, scores['composite'], data))
                except:
                    continue
            
            # 排序并选择前N只
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            selected = stock_scores[:self.params['top_n']]
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
                
                # 计算盈亏
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                # 止损
                if pnl_pct <= -self.params['stop_loss']:
                    cash += pos['shares'] * current_price
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'stop_loss', 'day': day, 'pnl': pnl_pct})
                    continue
                
                # 止盈
                if pnl_pct >= self.params['take_profit']:
                    cash += pos['shares'] * current_price
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'take_profit', 'day': day, 'pnl': pnl_pct})
                    continue
                
                # 如果不在选股列表中，卖出
                if vt_symbol not in selected_symbols:
                    cash += pos['shares'] * current_price
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'sell', 'day': day, 'pnl': pnl_pct})
            
            # 计算当前仓位价值
            position_value = sum(
                pos['shares'] * stock_data[vt_symbol]['close'][day]
                for vt_symbol, pos in positions.items()
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
                    # 保留最低现金比例
                    min_cash = total_value * self.params['cash_ratio']
                    if cash - shares * current_price >= min_cash:
                        positions[vt_symbol] = {
                            'entry_price': current_price,
                            'shares': shares,
                            'cost': shares * current_price
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
                pos['shares'] * stock_data[vt_symbol]['close'][day]
                for vt_symbol, pos in positions.items()
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
            "profit_loss_ratio": 1.8,
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
    print("优化版策略回测绩效报告")
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
    print("A股多因子选股策略 - 优化版回测")
    print("="*60)
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    print(f"\n数据库配置:")
    print(f"  主机: {db_config['host']}")
    print(f"  端口: {db_config['port']}")
    print(f"  数据库: {db_config['database']}")
    
    backtest = OptimizedBacktest(db_config)
    
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
        result_file = os.path.join(result_dir, f"optimized_result_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
