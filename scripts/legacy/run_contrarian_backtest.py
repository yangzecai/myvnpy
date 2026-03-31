#!/usr/bin/env python
"""
反向策略回测
基于真实数据回测结果，尝试反向操作

核心思想：
1. 选择得分低的股票（超跌反弹）
2. 大盘下跌时买入，上涨时卖出
3. 均值回归策略
"""

import os
import sys
import json
import math
import random
from datetime import datetime
from typing import Dict, List, Optional

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


class ContrarianBacktest:
    """反向策略回测引擎"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.calculator = OptimizedFactorCalculator()
        self.db = None
        self._init_database()
        
        # 反向策略参数
        self.params = {
            'bottom_n': 10,           # 选择得分最低的N只（超跌）
            'stop_loss': 0.05,        # 止损 5%
            'take_profit': 0.15,      # 止盈 15%
            'max_score': 0.0,         # 最高得分限制（选低分股）
            'min_score': -1.0,        # 最低得分限制
            'max_positions': 10,      # 最大持仓
            'position_size': 0.08,    # 单股仓位 8%
            'cash_ratio': 0.2,        # 最低现金比例 20%
            'rebalance_days': 5,      # 调仓周期（减少交易频率）
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
        """运行反向策略回测"""
        
        print("\n" + "="*60)
        print("反向策略回测（均值回归）")
        print("="*60)
        
        if not self.db:
            print("✗ 数据库未连接")
            return {}
        
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
        return self._simulate_trading(stock_data, start_date, end_date, initial_capital)
    
    def _simulate_trading(self, stock_data: Dict, 
                         start_date: str, end_date: str,
                         initial_capital: float) -> Dict:
        """模拟交易 - 反向策略"""
        
        first_stock = list(stock_data.values())[0]
        trading_days = len(first_stock['dates'])
        
        print(f"\n回测参数:")
        print(f"  交易日数: {trading_days}")
        print(f"  选股数量: {self.params['bottom_n']} (低分股)")
        print(f"  止损比例: {self.params['stop_loss']*100:.1f}%")
        print(f"  止盈比例: {self.params['take_profit']*100:.1f}%")
        print(f"  调仓周期: {self.params['rebalance_days']}天")
        print(f"  策略类型: 均值回归（反向操作）")
        
        print("\n模拟交易...")
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        # 持仓管理
        positions = {}
        cash = initial_capital
        
        for day in range(60, trading_days):
            # 只在调仓日进行调仓
            if (day - 60) % self.params['rebalance_days'] != 0 and day > 60:
                # 只检查止损止盈，不调仓
                for vt_symbol in list(positions.keys()):
                    if vt_symbol not in stock_data:
                        continue
                    
                    data = stock_data[vt_symbol]
                    if day >= len(data['close']):
                        continue
                    
                    current_price = data['close'][day]
                    pos = positions[vt_symbol]
                    pnl_pct = (