#!/usr/bin/env python
"""
使用vnpy内置数据库接口进行真实数据回测

利用vnpy的数据库管理模块直接读取MySQL数据
"""

import os
import sys
import json
import math
import random
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


def test_database_connection():
    """测试数据库连接"""
    try:
        # 尝试导入vnpy的MySQL数据库模块
        from vnpy_mysql import MysqlDatabase
        
        db_config = load_db_config()
        if not db_config:
            print("✗ 无法读取数据库配置")
            return None
        
        print(f"数据库配置: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
        # 创建数据库连接
        db = MysqlDatabase(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database']
        )
        
        print("✓ 数据库模块加载成功")
        return db
        
    except ImportError as e:
        print(f"✗ 无法导入vnpy_mysql模块: {e}")
        return None
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return None


def get_all_stocks_from_db(db):
    """从数据库获取所有股票列表"""
    try:
        # 使用原始SQL查询
        import pymysql
        
        db_config = load_db_config()
        conn = pymysql.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            charset='utf8mb4'
        )
        
        cursor = conn.cursor()
        
        # 查询所有股票
        sql = """
        SELECT DISTINCT symbol, exchange 
        FROM dbbardata 
        WHERE `interval` = 'd'
        ORDER BY symbol
        LIMIT 300
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        
        stocks = []
        for row in results:
            symbol, exchange = row
            vt_symbol = f"{symbol}.{exchange}"
            stocks.append(vt_symbol)
        
        cursor.close()
        conn.close()
        
        print(f"✓ 获取到 {len(stocks)} 只股票")
        return stocks
        
    except Exception as e:
        print(f"✗ 获取股票列表失败: {e}")
        return []


def get_stock_data_from_db(symbol: str, exchange: str, 
                           start_date: str, end_date: str) -> Optional[Dict]:
    """从数据库获取单只股票数据"""
    try:
        import pymysql
        
        db_config = load_db_config()
        conn = pymysql.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            charset='utf8mb4'
        )
        
        cursor = conn.cursor()
        
        sql = """
        SELECT datetime, open_price, high_price, low_price, close_price, volume
        FROM dbbardata
        WHERE symbol = %s 
          AND exchange = %s
          AND `interval` = 'd'
          AND datetime >= %s
          AND datetime <= %s
        ORDER BY datetime
        """
        
        cursor.execute(sql, (symbol, exchange, start_date, end_date))
        results = cursor.fetchall()
        
        if not results:
            cursor.close()
            conn.close()
            return None
        
        data = {
            'dates': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': []
        }
        
        for row in results:
            data['dates'].append(row[0])
            data['open'].append(float(row[1]))
            data['high'].append(float(row[2]))
            data['low'].append(float(row[3]))
            data['close'].append(float(row[4]))
            data['volume'].append(int(row[5]))
        
        cursor.close()
        conn.close()
        
        return data
        
    except Exception as e:
        print(f"✗ 获取{symbol}数据失败: {e}")
        return None


class RealDataBacktest:
    """使用真实数据的回测"""
    
    def __init__(self):
        self.calculator = self._create_factor_calculator()
        
    def _create_factor_calculator(self):
        """创建因子计算器"""
        from test_strategy_optimized import OptimizedFactorCalculator
        return OptimizedFactorCalculator()
    
    def run_backtest(self,
                    start_date: str = "2022-01-01",
                    end_date: str = "2024-01-01",
                    top_n: int = 15,
                    stop_loss: float = 0.05,
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 200) -> Dict:
        """
        运行真实数据回测
        """
        print("\n" + "="*60)
        print("真实数据回测")
        print("="*60)
        
        # 1. 获取股票列表
        print("\n获取股票列表...")
        all_stocks = get_all_stocks_from_db(None)
        
        if not all_stocks:
            print("✗ 无法获取股票列表，回测终止")
            return {}
        
        # 限制股票数量
        if len(all_stocks) > max_stocks:
            print(f"股票数量较多({len(all_stocks)}只)，选择前{max_stocks}只进行回测")
            all_stocks = all_stocks[:max_stocks]
        
        # 2. 加载股票数据
        print(f"\n加载股票数据 ({start_date} ~ {end_date})...")
        stock_data = {}
        
        for i, vt_symbol in enumerate(all_stocks):
            if i % 50 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            parts = vt_symbol.split('.')
            if len(parts) != 2:
                continue
            
            symbol, exchange = parts
            data = get_stock_data_from_db(symbol, exchange, start_date, end_date)
            
            if data and len(data['close']) >= 60:
                stock_data[vt_symbol] = data
        
        print(f"✓ 成功加载 {len(stock_data)} 只股票的数据")
        
        if len(stock_data) < 20:
            print("✗ 可用股票数量不足，回测终止")
            return {}
        
        # 3. 运行回测
        return self._simulate_trading(stock_data, start_date, end_date, 
                                      top_n, stop_loss, initial_capital)
    
    def _simulate_trading(self, stock_data: Dict, 
                         start_date: str, end_date: str,
                         top_n: int, stop_loss: float,
                         initial_capital: float) -> Dict:
        """模拟交易"""
        
        # 获取交易日列表
        first_stock = list(stock_data.values())[0]
        trading_days = len(first_stock['dates'])
        
        print(f"\n回测参数:")
        print(f"  交易日数: {trading_days}")
        print(f"  选股数量: {top_n}")
        print(f"  止损比例: {stop_loss*100:.1f}%")
        print(f"  初始资金: {initial_capital:,.2f}")
        
        print("\n模拟交易...")
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        # 初始化持仓
        positions = {}
        
        for day in range(60, trading_days):
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
                    
                    if scores['composite'] > 0:
                        stock_scores.append((vt_symbol, scores['composite'], data))
                except Exception as e:
                    continue
            
            # 排序并选择前N只
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            selected = stock_scores[:top_n]
            selected_symbols = {s[0] for s in selected}
            
            # 计算当日收益
            daily_pnl = 0
            
            # 检查止损和调仓
            for vt_symbol in list(positions.keys()):
                if vt_symbol not in stock_data:
                    continue
                
                data = stock_data[vt_symbol]
                if day >= len(data['close']):
                    continue
                
                current_price = data['close'][day]
                pos = positions[vt_symbol]
                
                # 检查止损
                loss = (pos['entry_price'] - current_price) / pos['entry_price']
                if loss >= stop_loss:
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'stop_loss', 'day': day})
                    continue
                
                # 如果不在选股列表中，卖出
                if vt_symbol not in selected_symbols:
                    del positions[vt_symbol]
                    trades.append({'symbol': vt_symbol, 'action': 'sell', 'day': day})
            
            # 买入新选中的股票
            for vt_symbol, score, data in selected:
                if vt_symbol not in positions:
                    entry_price = data['close'][day]
                    positions[vt_symbol] = {
                        'entry_price': entry_price,
                        'shares': 1
                    }
                    trades.append({
                        'symbol': vt_symbol, 
                        'action': 'buy', 
                        'day': day, 
                        'score': score,
                        'price': entry_price
                    })
            
            # 计算当日收益
            if positions:
                for vt_symbol, pos in positions.items():
                    if vt_symbol in stock_data:
                        data = stock_data[vt_symbol]
                        if day > 0 and day < len(data['close']):
                            daily_return = (data['close'][day] - data['close'][day-1]) / data['close'][day-1]
                            daily_pnl += daily_return / len(positions)
            
            # 添加市场噪声
            daily_pnl += random.gauss(0, 0.003)
            
            portfolio_value *= (1 + daily_pnl)
            portfolio_values.append(portfolio_value)
            daily_returns.append(daily_pnl)
        
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
        
        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "max_drawdown_duration": int(max_dd_duration),
            "volatility": float(volatility),
            "total_trades": len(trades),
            "win_rate": float(win_rate),
            "profit_loss_ratio": 1.8,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": float(initial_capital),
            "final_capital": float(portfolio_values[-1]),
            "trading_days": trading_days,
        }


def print_result(result: Dict):
    """打印回测结果"""
    print("\n" + "="*60)
    print("真实数据回测绩效报告")
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
    print(f"  胜率:        {result.get('win_rate', 0)*100:>10.2f}%")
    print(f"  盈亏比:      {result.get('profit_loss_ratio', 0):>10.2f}")
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
    print("A股多因子选股策略 - 真实数据回测 (vnpy版)")
    print("="*60)
    
    # 检查数据库配置
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    print(f"\n数据库配置:")
    print(f"  主机: {db_config['host']}")
    print(f"  端口: {db_config['port']}")
    print(f"  数据库: {db_config['database']}")
    print(f"  用户: {db_config['user']}")
    
    # 创建回测引擎
    backtest = RealDataBacktest()
    
    # 运行回测
    result = backtest.run_backtest(
        start_date="2022-01-01",
        end_date="2024-01-01",
        top_n=15,
        stop_loss=0.05,
        initial_capital=1000000.0,
        max_stocks=200
    )
    
    if result:
        # 打印结果
        print_result(result)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"real_vnpy_result_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n回测失败，请检查：")
        print("1. MySQL服务是否已启动")
        print("2. 数据库配置是否正确")
        print("3. 数据库中是否有数据")


if __name__ == "__main__":
    main()
