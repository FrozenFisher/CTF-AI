"""
训练可视化脚本
实时显示训练进度和统计信息，并提供终止建议
"""

import json
import os
import time
import matplotlib.pyplot as plt
from collections import deque
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class TrainingVisualizer:
    """训练可视化器"""
    
    def __init__(self, stats_file="models/training_stats.json", update_interval=5):
        self.stats_file = stats_file
        self.update_interval = update_interval
        self.stats_history = {
            'episodes': [],
            'rewards': deque(maxlen=100),
            'losses': deque(maxlen=100),
            'win_rates': deque(maxlen=100),
            'epsilon': deque(maxlen=100)
        }
        self.last_episode = 0
        
    def load_stats(self):
        """加载训练统计"""
        if not os.path.exists(self.stats_file):
            return None
        
        try:
            with open(self.stats_file, 'r') as f:
                stats = json.load(f)
            return stats
        except:
            return None
    
    def update_history(self, stats):
        """更新历史数据"""
        if stats is None:
            return
        
        episodes = stats.get('episode', 0)
        episode_rewards = stats.get('episode_rewards', [])
        losses = stats.get('losses', [])
        wins = stats.get('wins', 0)
        losses_count = stats.get('losses_count', 0)
        draws = stats.get('draws', 0)
        epsilon_history = stats.get('epsilon_history', [])
        
        # 只添加新的数据
        if episodes > self.last_episode:
            new_episodes = episodes - self.last_episode
            self.last_episode = episodes
            
            # 添加新的奖励数据
            if len(episode_rewards) > len(self.stats_history['rewards']):
                new_rewards = episode_rewards[-new_episodes:]
                self.stats_history['rewards'].extend(new_rewards)
            
            # 添加新的损失数据
            if len(losses) > len(self.stats_history['losses']):
                new_losses = losses[-new_episodes:]
                self.stats_history['losses'].extend(new_losses)
            
            # 计算胜率
            total_games = wins + losses_count + draws
            if total_games > 0:
                win_rate = wins / total_games * 100
                self.stats_history['win_rates'].append(win_rate)
            
            # 添加epsilon
            if len(epsilon_history) > len(self.stats_history['epsilon']):
                new_epsilon = epsilon_history[-new_episodes:]
                self.stats_history['epsilon'].extend(new_epsilon)
    
    def plot_stats(self, stats):
        """绘制统计图表"""
        if stats is None:
            print("等待训练数据...")
            return
        
        self.update_history(stats)
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('DQN训练进度监控', fontsize=16, fontweight='bold')
        
        episodes = stats.get('episode', 0)
        wins = stats.get('wins', 0)
        losses_count = stats.get('losses_count', 0)
        draws = stats.get('draws', 0)
        
        # 1. 奖励曲线
        ax1 = axes[0, 0]
        if len(self.stats_history['rewards']) > 0:
            rewards = list(self.stats_history['rewards'])
            window = min(20, len(rewards))
            if window > 0:
                # 计算移动平均
                moving_avg = []
                for i in range(len(rewards)):
                    start = max(0, i - window + 1)
                    moving_avg.append(np.mean(rewards[start:i+1]))
                
                ax1.plot(range(len(rewards)), rewards, alpha=0.3, color='blue', label='原始值')
                ax1.plot(range(len(moving_avg)), moving_avg, color='red', linewidth=2, label=f'{window}期移动平均')
                ax1.set_xlabel('Episode')
                ax1.set_ylabel('奖励')
                ax1.set_title('Episode奖励趋势')
                ax1.legend()
                ax1.grid(True, alpha=0.3)
        
        # 2. 损失曲线
        ax2 = axes[0, 1]
        if len(self.stats_history['losses']) > 0:
            losses = list(self.stats_history['losses'])
            window = min(20, len(losses))
            if window > 0:
                moving_avg = []
                for i in range(len(losses)):
                    start = max(0, i - window + 1)
                    moving_avg.append(np.mean(losses[start:i+1]))
                
                ax2.plot(range(len(losses)), losses, alpha=0.3, color='orange', label='原始值')
                ax2.plot(range(len(moving_avg)), moving_avg, color='red', linewidth=2, label=f'{window}期移动平均')
                ax2.set_xlabel('训练步数')
                ax2.set_ylabel('损失')
                ax2.set_title('训练损失趋势')
                ax2.legend()
                ax2.grid(True, alpha=0.3)
        
        # 3. 胜率曲线
        ax3 = axes[1, 0]
        if len(self.stats_history['win_rates']) > 0:
            win_rates = list(self.stats_history['win_rates'])
            window = min(20, len(win_rates))
            if window > 0:
                moving_avg = []
                for i in range(len(win_rates)):
                    start = max(0, i - window + 1)
                    moving_avg.append(np.mean(win_rates[start:i+1]))
                
                ax3.plot(range(len(win_rates)), win_rates, alpha=0.3, color='green', label='原始值')
                ax3.plot(range(len(moving_avg)), moving_avg, color='red', linewidth=2, label=f'{window}期移动平均')
                ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.5, label='50%基准线')
                ax3.set_xlabel('Episode')
                ax3.set_ylabel('胜率 (%)')
                ax3.set_title('胜率趋势')
                ax3.set_ylim([0, 100])
                ax3.legend()
                ax3.grid(True, alpha=0.3)
        
        # 4. 统计信息面板
        ax4 = axes[1, 1]
        ax4.axis('off')
        
        # 计算统计数据
        total_games = wins + losses_count + draws
        win_rate = wins / total_games * 100 if total_games > 0 else 0
        
        recent_rewards = list(self.stats_history['rewards'])[-10:] if len(self.stats_history['rewards']) > 0 else []
        avg_reward = np.mean(recent_rewards) if recent_rewards else 0
        
        recent_losses = list(self.stats_history['losses'])[-10:] if len(self.stats_history['losses']) > 0 else []
        avg_loss = np.mean(recent_losses) if recent_losses else 0
        
        current_epsilon = stats.get('epsilon_history', [])[-1] if stats.get('epsilon_history') else 0
        
        # 显示文本信息
        info_text = f"""
训练统计信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总Episode数: {episodes}
总对局数: {total_games}
  胜: {wins} ({win_rate:.1f}%)
  负: {losses_count} ({losses_count/total_games*100 if total_games > 0 else 0:.1f}%)
  平: {draws} ({draws/total_games*100 if total_games > 0 else 0:.1f}%)

最近10局平均奖励: {avg_reward:.2f}
最近10局平均损失: {avg_loss:.4f}
当前探索率 (ε): {current_epsilon:.4f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
训练建议:
{self.get_training_advice(stats)}
        """
        
        ax4.text(0.1, 0.5, info_text, fontsize=11, family='monospace',
                verticalalignment='center', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        return fig
    
    def get_training_advice(self, stats):
        """获取训练建议"""
        if stats is None:
            return "等待训练数据..."
        
        episodes = stats.get('episode', 0)
        wins = stats.get('wins', 0)
        losses_count = stats.get('losses_count', 0)
        draws = stats.get('draws', 0)
        total_games = wins + losses_count + draws
        
        if total_games == 0:
            return "训练刚开始，继续观察..."
        
        win_rate = wins / total_games * 100
        recent_rewards = stats.get('episode_rewards', [])[-20:]
        recent_losses = stats.get('losses', [])[-20:]
        
        advice = []
        
        # 胜率建议
        if win_rate >= 80:
            advice.append("✓ 胜率很高(≥80%)，模型表现优秀")
            advice.append("  可以考虑停止训练或保存模型")
        elif win_rate >= 60:
            advice.append("✓ 胜率良好(≥60%)，模型表现不错")
            advice.append("  可以继续训练以进一步提升")
        elif win_rate >= 50:
            advice.append("○ 胜率中等(≥50%)，模型表现一般")
            advice.append("  建议继续训练")
        else:
            advice.append("⚠ 胜率较低(<50%)，模型需要更多训练")
            advice.append("  建议继续训练或调整超参数")
        
        # 收敛性检查
        if len(recent_rewards) >= 10:
            reward_std = np.std(recent_rewards)
            if reward_std < 10 and episodes > 50:
                advice.append("✓ 奖励趋于稳定，可能已收敛")
            elif reward_std > 50:
                advice.append("⚠ 奖励波动较大，训练不稳定")
        
        # Episode数量建议
        if episodes < 50:
            advice.append("○ 训练初期，建议至少训练100个episode")
        elif episodes < 200:
            advice.append("○ 训练中期，建议继续训练到200+ episode")
        else:
            advice.append("✓ 训练已进行较长时间")
            if win_rate >= 70:
                advice.append("  如果胜率稳定，可以考虑停止")
        
        # 损失检查
        if len(recent_losses) >= 10:
            avg_loss = np.mean(recent_losses)
            if avg_loss < 0.1:
                advice.append("✓ 损失已降至较低水平")
            elif avg_loss > 1.0:
                advice.append("⚠ 损失较高，可能需要调整学习率")
        
        return "\n".join(advice) if advice else "继续训练..."
    
    def run(self, save_plot=True):
        """运行可视化"""
        print("=" * 60)
        print("训练可视化监控")
        print("=" * 60)
        print(f"监控文件: {self.stats_file}")
        print(f"更新间隔: {self.update_interval}秒")
        print("按 Ctrl+C 停止监控")
        print("=" * 60)
        
        try:
            while True:
                stats = self.load_stats()
                
                if stats:
                    episodes = stats.get('episode', 0)
                    print(f"\r[更新] Episode {episodes} | ", end='', flush=True)
                    
                    # 绘制图表
                    fig = self.plot_stats(stats)
                    if fig:
                        if save_plot:
                            plot_path = "models/training_plot.png"
                            fig.savefig(plot_path, dpi=150, bbox_inches='tight')
                            print(f"图表已保存: {plot_path}")
                        
                        plt.show(block=False)
                        plt.pause(0.1)
                
                time.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            print("\n\n监控已停止")
            plt.close('all')


def main():
    """主函数"""
    import sys
    
    stats_file = sys.argv[1] if len(sys.argv) > 1 else "models/training_stats.json"
    update_interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    visualizer = TrainingVisualizer(stats_file, update_interval)
    visualizer.run()


if __name__ == "__main__":
    main()

