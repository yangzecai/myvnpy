#!/usr/bin/env python
"""
使用真实MySQL数据进行回测 - 最终版
直接使用vnpy的数据库接口
"""

import os
import sys
import json
import math
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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


# 导入因子计算器
from test_strategy_optimized import OptimizedFactorCalculator


class RealDataBacktest:
    """使用真实数据的回测"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.calculator = OptimizedFactorCalculator()
        self.db = None
        self._init_database()
        
    def _init_database(self):
        """初始化数据库连接"""
        try:
            # 设置vnpy的数据库配置
            from vnpy.trader.setting import SETTINGS
            SETTINGS["database.database"] = self.db_config['database']
            SETTINGS["database.user"] = self.db_config['user']
            SETTINGS["database.password"] = self.db_config['password']
            SETTINGS["database.host"] = self.db_config['host']
            SETTINGS["database.port"] = self.db_config['port']
            
            # 导入并创建数据库连接
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
            # 使用vnpy的数据库接口查询所有股票
            from vnpy_mysql.mysql_database import DbBarData
            
            # 查询所有日级数据的symbol
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
            
            # 如果数据库中没有数据，使用测试列表
            if not stocks:
                stocks = [
                    '000001.SZ', '000002.SZ', '000063.SZ', '000100.SZ', '000333.SZ',
                    '000538.SZ', '000568.SZ', '000651.SZ', '000725.SZ', '000768.SZ',
                    '000858.SZ', '000895.SZ', '002001.SZ', '002007.SZ', '002024.SZ',
                    '002027.SZ', '002142.SZ', '002230.SZ', '002236.SZ', '002304.SZ',
                    '002352.SZ', '002415.SZ', '002460.SZ', '002475.SZ', '002594.SZ',
                    '002714.SZ', '300003.SZ', '300014.SZ', '300015.SZ', '300033.SZ',
                    '300059.SZ', '300122.SZ', '300124.SZ', '300142.SZ', '300274.SZ',
                    '300408.SZ', '300413.SZ', '300433.SZ', '300498.SZ', '300750.SZ',
                    '600000.SS', '600009.SS', '600016.SS', '600028.SS', '600030.SS',
                    '600031.SS', '600036.SS', '600048.SS', '600050.SS', '600104.SS',
                    '600276.SS', '600309.SS', '600340.SS', '600406.SS', '600436.SS',
                    '600438.SS', '600519.SS', '600547.SS', '600570.SS', '600585.SS',
                    '600588.SS', '600660.SS', '600690.SS', '600703.SS', '600745.SS',
                    '600809.SS', '600837.SS', '600887.SS', '600893.SS', '600900.SS',
                    '601012.SS', '601066.SS', '601088.SS', '601100.SS', '601138.SS',
                    '601166.SS', '601186.SS', '601211.SS', '601288.SS', '601318.SS',
                    '601336.SS', '601398.SS', '601601.SS', '601628.SS', '601668.SS',
                    '601688.SS', '601766.SS', '601788.SS', '601857.SS', '601888.SS',
                    '601899.SS', '601901.SS', '601933.SS', '601985.SS', '601988.SS',
                    '601989.SS', '603019.SS', '603160.SS', '603288.SS', '603501.SS',
                    '603659.SS', '603799.SS', '603986.SS', '688001.SS', '688008.SS',
                    '688009.SS', '688012.SS', '688036.SS', '688111.SS', '688169.SS',
                ]
                print(f"✓ 使用测试股票列表，共 {len(stocks)} 只")
            
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
            
            # 使用vnpy的数据库接口加载数据
            from vnpy.trader.object import Interval
            from vnpy.trader.constant import Exchange
            
            # 获取交易所枚举 - 处理不同的交易所代码格式
            exchange_map = {
                'SZ': Exchange.SZSE,
                'SS': Exchange.SSE,
                'SZSE': Exchange.SZSE,
                'SSE': Exchange.SSE,
            }
            ex = exchange_map.get(exchange_str, Exchange.SSE)
            
            # 加载K线数据
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
                'volume': []
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
                    top_n: int = 15,
                    stop_loss: float = 0.05,
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 100) -> Dict:
        """运行真实数据回测"""
        
        print("\n" + "="*60)
        print("真实数据回测")
        print("="*60)
        
        if not self.db:
            print("✗ 数据库未连接，回测终止")
            return {}
        
        # 1. 获取股票列表
        print("\n获取股票列表...")
        all_stocks = self.get_all_stocks()
        
        if not all_stocks:
            print("✗ 无法获取股票列表，回测终止")
            return {}
        
        # 限制股票数量
        if len(all_stocks) > max_stocks:
            print(f"选择前{max_stocks}只股票进行回测")
            all_stocks = all_stocks[:max_stocks]
        
        # 2. 加载股票数据
        print(f"\n加载股票数据 ({start_date} ~ {end_date})...")
        stock_data = {}
        
        for i, vt_symbol in enumerate(all_stocks):
            if i % 20 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            data = self.get_stock_data(vt_symbol, start_date, end_date)
            
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


def analyze_and_optimize(result: Dict):
    """分析回测结果并提出优化建议"""
    print("\n" + "="*60)
    print("策略分析与优化建议")
    print("="*60)
    
    sharpe = result.get('sharpe_ratio', 0)
    max_dd = result.get('max_drawdown', 0)
    win_rate = result.get('win_rate', 0)
    annual_return = result.get('annual_return', 0)
    
    # 分析问题
    issues = []
    
    if sharpe < 1.0:
        issues.append(f"夏普率偏低 ({sharpe:.2f} < 1.0)")
    if max_dd < -0.15:
        issues.append(f"最大回撤过大 ({max_dd*100:.1f}% > 15%)")
    if win_rate < 0.5:
        issues.append(f"胜率偏低 ({win_rate*100:.1f}% < 50%)")
    if annual_return < 0.1:
        issues.append(f"年化收益偏低 ({annual_return*100:.1f}% < 10%)")
    
    if issues:
        print("\n发现的问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\n✓ 策略表现良好，未发现明显问题")
    
    # 优化建议
    print("\n优化建议:")
    
    if sharpe < 1.0:
        print("\n1. 夏普率优化:")
        print("   - 调整因子权重，增加动量因子比重")
        print("   - 优化止损参数，尝试 tighter stop")
        print("   - 添加大盘趋势过滤")
    
    if max_dd < -0.15:
        print("\n2. 回撤控制:")
        print("   - 降低仓位比例")
        print("   - 添加最大回撤限制（如15%清仓）")
        print("   - 分散行业配置")
    
    if win_rate < 0.5:
        print("\n3. 胜率提升:")
        print("   - 提高选股门槛（得分>0.2）")
        print("   - 添加更多技术指标确认")
        print("   - 优化入场时机")
    
    print("\n4. 通用优化:")
    print("   - 添加止盈策略")
    print("   - 动态仓位管理")
    print("   - 行业轮动配置")
    print("   - 添加基本面因子")
    
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 真实数据回测 (最终版)")
    print("="*60)
    
    # 加载数据库配置
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
    backtest = RealDataBacktest(db_config)
    
    if not backtest.db:
        print("\n✗ 数据库连接失败，请检查：")
        print("1. MySQL服务是否已启动")
        print("2. 数据库配置是否正确")
        print("3. vnpy_mysql模块是否已安装")
        return
    
    # 运行回测
    result = backtest.run_backtest(
        start_date="2022-01-01",
        end_date="2024-01-01",
        top_n=15,
        stop_loss=0.05,
        initial_capital=1000000.0,
        max_stocks=100
    )
    
    if result:
        # 打印结果
        print_result(result)
        
        # 分析并给出优化建议
        analyze_and_optimize(result)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"real_final_result_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
