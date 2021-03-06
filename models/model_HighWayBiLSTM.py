# coding=utf-8
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
import random
import numpy as np
import torch.nn.init as init
import hyperparams
torch.manual_seed(hyperparams.seed_num)
random.seed(hyperparams.seed_num)

# HighWay Networks model
class HighwayBiLSTM(nn.Module):

    def __init__(self, args):
        super(HighwayBiLSTM, self).__init__()
        self.args = args
        self.hidden_dim = args.lstm_hidden_dim
        self.num_layers = args.lstm_num_layers
        V = args.embed_num
        D = args.embed_dim
        self.C = args.class_num
        self.bilstm = nn.LSTM(D, self.hidden_dim, num_layers=self.num_layers, bias=True, bidirectional=True
                              , dropout=args.dropout)
        in_feas = self.hidden_dim
        self.fc1 = self.init_Linear(in_fea=in_feas, out_fea=in_feas, bias=True)
        # Highway gate layer  T in the Highway formula
        self.gate_layer = self.init_Linear(in_fea=in_feas, out_fea=in_feas, bias=True)
        # if bidirection convert dim
        self.convert_layer = self.init_Linear(in_fea=self.args.lstm_hidden_dim * 2,
                                              out_fea=self.args.embed_dim, bias=True)
        self.hidden = self.init_hidden(self.num_layers, args.batch_size)

    def init_hidden(self, num_layers, batch_size):
        # the first is the hidden h
        # the second is the cell  c
        return (Variable(torch.zeros(2 * num_layers, batch_size, self.hidden_dim)),
                Variable(torch.zeros(2 * num_layers, batch_size, self.hidden_dim)))

    def init_Linear(self, in_fea, out_fea, bias):
        linear = nn.Linear(in_features=in_fea, out_features=out_fea, bias=bias)
        return linear

    def forward(self, x, hidden):
        # print(x.size())
        # print(hidden)
        # handle the source input x
        # sourxe_x = x
        # sourxe_x = F.max_pool1d(sourxe_x.permute(1, 2, 0), sourxe_x.size(0)).squeeze(2)
        # print("source x {} ".format(sourxe_x.size()))
        x, hidden = self.bilstm(x, hidden)
        # print("aaaaa", x.size())
        x = torch.transpose(x, 0, 1)
        x = torch.transpose(x, 1, 2)
        # print(x.size())
        # normal layer in the formula is H
        out_fea = x.size(2)
        self.fc1 = self.init_Linear(in_fea=out_fea, out_fea=out_fea, bias=True)
        self.gate_layer = self.init_Linear(in_fea=out_fea, out_fea=out_fea, bias=True)
        # print(self.fc1)
        # print(self.gate_layer)
        list = []
        for i in range(x.size(0)):
            # normal_fc = F.tanh(self.fc1(x[i]))
            # normal_fc = F.tanh(x[i])
            normal_fc = x[i]
            # print("norm ", normal_fc.size())
            # transformation gate layer in the formula is T
            transformation_layer = F.sigmoid(self.gate_layer(x[i]))
            # transformation_layer = F.sigmoid(self.gate_layer(sourxe_x))
            # print("trans {} ".format(transformation_layer.size()))
            # carry gate layer in the formula is C
            carry_layer = 1 - transformation_layer
            # formula Y = H * T + x * C
            allow_transformation = torch.mul(normal_fc, transformation_layer)
            # print("carry size {} ".format(carry_layer.size()))
            allow_carry = torch.mul(x[i], carry_layer)
            information_flow = torch.add(allow_transformation, allow_carry)
            # convert the dim im bidirection
            # print(information_flow.size())
            information_flow = self.convert_layer(torch.transpose(information_flow, 0, 1))
            # follow for the next input
            # information_flow = normal_fc
            # print(information_flow.size())
            information_flow = information_flow.unsqueeze(0)
            list.append(information_flow)
        information_flow = torch.cat(list, 0)
        # print("dfff", information_flow.size())
        # information_flow = torch.transpose(information_flow, 1, 2)
        information_flow = torch.transpose(information_flow, 0, 1)
        # print(information_flow.size())
        return information_flow, hidden
        # return x, hidden


# HighWay recurrent model
class HighWayBiLSTM_model(nn.Module):

    def __init__(self, args):
        super(HighWayBiLSTM_model, self).__init__()
        self.args = args
        self.hidden_dim = args.lstm_hidden_dim
        self.num_layers = args.lstm_num_layers
        V = args.embed_num
        D = args.embed_dim
        self.C = args.class_num
        self.embed = nn.Embedding(V, D)
        self.dropout = nn.Dropout(args.dropout)
        self.dropout_embed = nn.Dropout(args.dropout_embed)
        if args.word_Embedding is True:
            pretrained_weight = np.array(args.pretrained_weight)
            self.embed.weight.data.copy_(torch.from_numpy(pretrained_weight))
        # multiple HighWay layers List
        self.highway = nn.ModuleList([HighwayBiLSTM(args) for _ in range(args.layer_num_highway)])
        self.output_layer = self.init_Linear(in_fea=self.args.embed_dim, out_fea=self.C, bias=True)
        self.hidden = self.init_hidden(self.num_layers, args.batch_size)

    def init_Linear(self, in_fea, out_fea, bias):
        linear = nn.Linear(in_features=in_fea, out_features=out_fea, bias=bias)
        return linear

    def init_hidden(self, num_layers, batch_size):
        # the first is the hidden h
        # the second is the cell  c
        return (Variable(torch.zeros(2 * num_layers, batch_size, self.hidden_dim)),
                Variable(torch.zeros(2 * num_layers, batch_size, self.hidden_dim)))

    def forward(self, x):
        x = self.embed(x)
        x = self.dropout_embed(x)
        # print(x.size())
        # self.output_layer = self.init_Linear(in_fea=self.args.lstm_hidden_dim * 2, out_fea=self.C, bias=True)
        for current_layer in self.highway:
            self.hidden = self.init_hidden(self.num_layers, x.size(1))
            # print(self.hidden)
            # print(current_layer)
            x, self.hidden = current_layer(x, self.hidden)

        # print(x.size())
        x = torch.transpose(x, 0, 1)
        x = torch.transpose(x, 1, 2)
        x = F.tanh(x)
        x = F.max_pool1d(x, x.size(2)).squeeze(2)
        x = F.tanh(x)
        output_layer = self.output_layer(x)
        # print(output_layer.size())
        return output_layer








