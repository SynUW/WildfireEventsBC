"""
Is Mamba Effective for Time Series Forecasting?
"""
import torch
import torch.nn as nn
import os
import sys

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from model_zoo_10x.layers.Mamba_EncDec import Encoder, EncoderLayer
from model_zoo_10x.layers.Embed import DataEmbedding_inverted
import datetime
import numpy as np

from mamba_ssm import Mamba

class Configs:
    def __init__(self, seq_len=10, pred_len=7, d_model=390, d_state=160, d_ff=2560, 
                 e_layers=20, dropout=0.1, activation='relu', output_attention=False,
                 use_norm=True, embed='timeF', freq='d'):
        # 模型基本参数
        self.seq_len = seq_len  # 输入序列长度
        self.pred_len = pred_len  # 预测长度
        self.d_model = d_model  # 模型维度 (扩大10倍: 39 -> 390)
        self.d_state = d_state  # SSM状态扩展因子 (扩大10倍: 16 -> 160)
        self.d_ff = d_ff   # 前馈网络维度 (扩大10倍: 256 -> 2560)
        
        # 模型结构参数
        self.e_layers = e_layers  # 编码器层数 (扩大10倍: 2 -> 20)
        self.dropout = dropout  # dropout率
        self.activation = activation  # 激活函数
        
        # 其他参数
        self.output_attention = output_attention  # 是否输出注意力权重
        self.use_norm = use_norm  # 是否使用归一化
        self.embed = embed  # 嵌入类型
        self.freq = freq  # 频率

class Model(nn.Module):
    """
    Paper link: https://arxiv.org/abs/2310.06625
    """

    def __init__(self, configs):
        super(Model, self).__init__()
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        self.output_attention = configs.output_attention
        self.use_norm = configs.use_norm
        # Embedding - 第一个参数应该是序列长度
        self.enc_embedding = DataEmbedding_inverted(configs.seq_len, configs.d_model, configs.embed, configs.freq,
                                                    configs.dropout)
        # Encoder-only architecture
        self.encoder = Encoder(
            [
                EncoderLayer(
                        Mamba(
                            d_model=configs.d_model,  # Model dimension d_model
                            d_state=configs.d_state,  # SSM state expansion factor
                            d_conv=2,  # Local convolution width
                            expand=1,  # Block expansion factor)
                        ),
                        Mamba(
                            d_model=configs.d_model,  # Model dimension d_model
                            d_state=configs.d_state,  # SSM state expansion factor
                            d_conv=2,  # Local convolution width
                            expand=1,  # Block expansion factor)
                        ),
                    configs.d_model,
                    configs.d_ff,
                    dropout=configs.dropout,
                    activation=configs.activation
                ) for l in range(configs.e_layers)
            ],
            norm_layer=torch.nn.LayerNorm(configs.d_model)
        )
        self.projector = nn.Linear(configs.d_model, configs.pred_len, bias=True)

    def forecast(self, x_enc, x_mark_enc):
        if self.use_norm:
            # Normalization from Non-stationary Transformer
            means = x_enc.mean(1, keepdim=True).detach()
            x_enc = x_enc - means
            stdev = torch.sqrt(torch.var(x_enc, dim=1, keepdim=True, unbiased=False) + 1e-5)
            x_enc /= stdev

        _, _, N = x_enc.shape # B L N
        # B: batch_size;    E: d_model; 
        # L: seq_len;       S: pred_len;
        # N: number of variate (tokens), can also includes covariates

        # Embedding
        # B L N -> B N E                (B L N -> B L E in the vanilla Transformer)
        enc_out = self.enc_embedding(x_enc, x_mark_enc) # covariates (e.g timestamp) can be also embedded as tokens
        
        # B N E -> B N E                (B L E -> B L E in the vanilla Transformer)
        # the dimensions of embedded time series has been inverted, and then processed by native attn, layernorm and ffn modules
        enc_out, attns = self.encoder(enc_out, attn_mask=None)
        # B N E -> B N S -> B S N 
        dec_out = self.projector(enc_out).permute(0, 2, 1)[:, :, :N] # filter the covariates

        if self.use_norm:
            # De-Normalization from Non-stationary Transformer
            dec_out = dec_out * (stdev[:, 0, :].unsqueeze(1).repeat(1, self.pred_len, 1))
            dec_out = dec_out + (means[:, 0, :].unsqueeze(1).repeat(1, self.pred_len, 1))

        return dec_out


    def forward(self, x_enc, target_date, mask=None):
        # x_enc: [B, L, D] 其中 L=10 表示前10天的数据
        # target_date: [B] 格式为 yyyymmdd 的日期字符串列表
        
        batch_size, seq_len, _ = x_enc.shape
        device = x_enc.device  # 获取输入张量的设备
        
        # 创建时间编码
        time_encodings = []
        for date_str in target_date:
            # 解析日期
            year = int(str(date_str)[:4])
            month = int(str(date_str)[4:6])
            day = int(str(date_str)[6:8])
            
            # 计算星期几 (0-6, 0表示星期一)
            weekday = datetime.datetime(year, month, day).weekday()
            
            # 计算一年中的第几天 (1-366)
            day_of_year = datetime.datetime(year, month, day).timetuple().tm_yday
            
            # 创建时间编码
            # 1. 月份编码 (1-12)
            month_sin = torch.sin(torch.tensor(2 * np.pi * month / 12, device=device))
            month_cos = torch.cos(torch.tensor(2 * np.pi * month / 12, device=device))
            
            # 2. 星期编码 (0-6)
            weekday_sin = torch.sin(torch.tensor(2 * np.pi * weekday / 7, device=device))
            weekday_cos = torch.cos(torch.tensor(2 * np.pi * weekday / 7, device=device))
            
            # 3. 一年中的第几天编码 (1-366)
            day_sin = torch.sin(torch.tensor(2 * np.pi * day_of_year / 366, device=device))
            day_cos = torch.cos(torch.tensor(2 * np.pi * day_of_year / 366, device=device))
            
            # 组合时间特征
            time_encoding = torch.tensor([month_sin, month_cos, 
                                        weekday_sin, weekday_cos,
                                        day_sin, day_cos], device=device)
            time_encodings.append(time_encoding)
        
        # 将时间编码转换为张量 [B, 6]
        x_mark_enc = torch.stack(time_encodings)
        # 扩展维度以匹配序列长度 [B, L, 6]
        x_mark_enc = x_mark_enc.unsqueeze(1).repeat(1, seq_len, 1)
        
        dec_out = self.forecast(x_enc, x_mark_enc)
        return dec_out[:, -self.pred_len:, :]  # [B, L, D]
    
    
if __name__ == '__main__':
    configs = Configs(
    seq_len=10,
    pred_len=7,
    d_model=390,  # 扩大10倍
    d_state=160,  # 扩大10倍
    d_ff=2560,    # 扩大10倍
    e_layers=20,  # 扩大10倍
    dropout=0.1,
)
    # 创建模型并移动到 GPU
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = Model(configs).to(device)
    
    # 测试数据
    batch_size = 32
    x_enc = torch.randn(batch_size, configs.seq_len, 39).to(device)  # [32, 10, 39] - 输入维度保持39
    target_date = ['20010829'] * batch_size  # 示例日期
    
    # 前向传播测试
    output = model(x_enc, target_date)
    print(f"Input shape: {x_enc.shape}")
    print(f"Output shape: {output.shape}")
    
    # 计算参数量
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Total parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}") 