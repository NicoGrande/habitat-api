#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import torch
import torch.nn as nn

import numpy as np


def conv3x3(in_planes, out_planes, stride=1, groups=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(
        in_planes,
        out_planes,
        kernel_size=3,
        stride=stride,
        padding=1,
        bias=False,
        groups=groups,
    )


def conv1x1(in_planes, out_planes, stride=1):
    """1x1 convolution"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, bias=False)


class BasicBlock(nn.Module):
    expansion = 1
    resneXt = False

    def __init__(
        self, inplanes, planes, ngroups, stride=1, downsample=None, cardinality=1,
    ):
        super(BasicBlock, self).__init__()
        self.convs = nn.Sequential(
            conv3x3(inplanes, planes, stride, groups=cardinality),
            nn.GroupNorm(ngroups, planes),
            nn.ReLU(True),
            conv3x3(planes, planes, groups=cardinality),
            nn.GroupNorm(ngroups, planes),
        )
        self.downsample = downsample
        self.relu = nn.ReLU(True)

    def forward(self, x):
        residual = x

        out = self.convs(x)

        if self.downsample is not None:
            residual = self.downsample(x)

        return self.relu(out + residual)


def _build_bottleneck_branch(inplanes, planes, ngroups, stride, expansion, groups=1):
    return nn.Sequential(
        conv1x1(inplanes, planes),
        nn.GroupNorm(ngroups, planes),
        nn.ReLU(True),
        conv3x3(planes, planes, stride, groups=groups),
        nn.GroupNorm(ngroups, planes),
        nn.ReLU(True),
        conv1x1(planes, planes * expansion),
        nn.GroupNorm(ngroups, planes * expansion),
    )


class SE(nn.Module):
    def __init__(self, planes, r=16):
        super().__init__()
        self.squeeze = nn.AdaptiveAvgPool2d(1)
        self.excite = nn.Sequential(
            nn.Linear(planes, int(planes / r)),
            nn.ReLU(True),
            nn.Linear(int(planes / r), planes),
            nn.Sigmoid(),
        )

    def forward(self, x):
        b, c, _, _ = x.size()
        x = self.squeeze(x)
        x = x.view(b, c)
        x = self.excite(x)

        return x.view(b, c, 1, 1)


def _build_se_branch(planes, r=16):
    return SE(planes, r)


class Bottleneck(nn.Module):
    expansion = 4
    resneXt = False

    def __init__(
        self, inplanes, planes, ngroups, stride=1, downsample=None, cardinality=1,
    ):
        super().__init__()
        self.convs = _build_bottleneck_branch(
            inplanes, planes, ngroups, stride, self.expansion, groups=cardinality,
        )
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample

    def _impl(self, x):
        identity = x

        out = self.convs(x)

        if self.downsample is not None:
            identity = self.downsample(x)

        return self.relu(out + identity)

    def forward(self, x):
        return self._impl(x)


class SEBottleneck(Bottleneck):
    def __init__(
        self, inplanes, planes, ngroups, stride=1, downsample=None, cardinality=1,
    ):
        super().__init__(inplanes, planes, ngroups, stride, downsample, cardinality)

        self.se = _build_se_branch(planes * self.expansion)

    def _impl(self, x):
        identity = x

        out = self.convs(x)
        out = self.se(out) * out

        if self.downsample is not None:
            identity = self.downsample(x)

        return self.relu(out + identity)


class SEResNeXtBottleneck(SEBottleneck):
    expansion = 2
    resneXt = True


class ResNeXtBottleneck(Bottleneck):
    expansion = 2
    resneXt = True


class ResNet(nn.Module):
    def __init__(self, in_channels, base_planes, ngroups, block, layers, cardinality=1):
        super(ResNet, self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(
                in_channels,
                base_planes,
                kernel_size=7,
                stride=2,
                padding=3,
                bias=False,
            ),
            nn.GroupNorm(ngroups, base_planes),
            nn.ReLU(True),
        )
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.cardinality = cardinality

        self.inplanes = base_planes
        if block.resneXt:
            base_planes *= 2

        self.layer1 = self._make_layer(block, ngroups, base_planes, layers[0])
        self.layer2 = self._make_layer(
            block, ngroups, base_planes * 2, layers[1], stride=2
        )
        self.layer3 = self._make_layer(
            block, ngroups, base_planes * 2 * 2, layers[2], stride=2
        )
        self.layer4 = self._make_layer(
            block, ngroups, base_planes * 2 * 2 * 2, layers[3], stride=2
        )

        self.final_channels = self.inplanes

        self.spatial_compression_steps = 5

    def _make_layer(self, block, ngroups, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                conv1x1(self.inplanes, planes * block.expansion, stride),
                nn.GroupNorm(ngroups, planes * block.expansion),
            )

        layers = []
        layers.append(
            block(
                self.inplanes,
                planes,
                ngroups,
                stride,
                downsample,
                cardinality=self.cardinality,
            )
        )
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes, ngroups))

        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.conv1(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        return x


def resnet18(in_channels, base_planes, ngroups):
    model = ResNet(in_channels, base_planes, ngroups, BasicBlock, [2, 2, 2, 2])

    return model


def resnet50(in_channels, base_planes, ngroups):
    model = ResNet(in_channels, base_planes, ngroups, Bottleneck, [3, 4, 6, 3])

    return model


def resneXt50(in_channels, base_planes, ngroups):
    model = ResNet(
        in_channels,
        base_planes,
        ngroups,
        ResNeXtBottleneck,
        [3, 4, 6, 3],
        cardinality=int(base_planes / 2),
    )

    return model


def se_resnet50(in_channels, base_planes, ngroups):
    model = ResNet(in_channels, base_planes, ngroups, SEBottleneck, [3, 4, 6, 3])

    return model


def se_resneXt50(in_channels, base_planes, ngroups):
    model = ResNet(
        in_channels,
        base_planes,
        ngroups,
        SEResNeXtBottleneck,
        [3, 4, 6, 3],
        cardinality=int(base_planes / 2),
    )

    return model


def se_resneXt101(in_channels, base_planes, ngroups):
    model = ResNet(
        in_channels,
        base_planes,
        ngroups,
        SEResNeXtBottleneck,
        [3, 4, 23, 3],
        cardinality=int(base_planes / 2),
    )

    return model

class Flatten(nn.Module):
    def forward(self, x):
        return x.view(x.size(0), -1)

class ResNetEncoderForOdometer(nn.Module):
    def __init__(
        self,
        input_dims=(360, 640),
        input_channels=1,
        repr_size=512,
        baseplanes=32,
        ngroups=32,
        spatial_size=128,
    ):
        super().__init__()

        self.repr_size = repr_size

        self._n_input_rgb, self._n_input_depth = 0, 0
        if input_channels == 1:
            self._n_input_rgb, self._n_input_depth = 0, 1
        if input_channels == 3:
            self._n_input_rgb, self._n_input_depth = 3, 0
        if input_channels == 4:
            self._n_input_rgb, self._n_input_depth = 3, 1
        
        self._n_input_rgb *= 2
        self._n_input_depth *= 2
        spatial_size = input_dims
        self.running_mean_and_var = nn.Sequential()

        if not self.is_blind:
            self.initial_pool = nn.AvgPool2d(3)
            input_channels = self._n_input_depth + self._n_input_rgb
            self.backbone = resnet18(input_channels, baseplanes, ngroups)

            spatial_size = tuple(int((s - 1) // 3 + 1) for s in spatial_size)
            for _ in range(self.backbone.spatial_compression_steps):
                spatial_size = tuple(int((s - 1) // 2 + 1) for s in spatial_size)

            self.output_shape = (
                self.backbone.final_channels,
                spatial_size[0],
                spatial_size[1],
            )

            after_compression_flat_size = 2048
            num_compression_channels = int(
                round(after_compression_flat_size / np.prod(spatial_size))
            )
            self.compression = nn.Sequential(
                nn.Conv2d(
                    self.output_shape[0],
                    num_compression_channels,
                    kernel_size=3,
                    padding=1,
                    bias=False,
                ),
                nn.GroupNorm(1, num_compression_channels),
                nn.ReLU(True),
            )

            compression_shape = list(self.output_shape)
            compression_shape[0] = num_compression_channels
            self.compression_shape = tuple(compression_shape)

            self.output_shape = self.compression_shape
            self.visual_fc = nn.Sequential(
                Flatten(),
                nn.Linear(
                    np.prod(self.output_shape), self.repr_size
                ),
                nn.ReLU(True),
            )
            self.layer_init()

    @property
    def is_blind(self):
        return self._n_input_rgb + self._n_input_depth == 0

    def layer_init(self):
        for layer in self.modules():
            if isinstance(layer, (nn.Conv2d, nn.Linear)):
                nn.init.kaiming_normal_(layer.weight, nn.init.calculate_gain("relu"))
                if layer.bias is not None:
                    nn.init.constant_(layer.bias, val=0)

    def forward(self, batch):
        if self.is_blind:
            return None

        source_input, target_input = [], []
        if self._n_input_rgb > 0:
            source_images, target_images = torch.split(batch, split_size_or_sections=1, dim=1)
            source_input += [source_images]
            target_input += [target_images]

        if self._n_input_depth > 0:
            source_depth_maps, target_depth_maps = torch.split(batch, split_size_or_sections=1, dim=1)
            source_input += [source_depth_maps]
            target_input += [target_depth_maps]
        
        concat_source_input = torch.cat(source_input, 1)
        concat_target_input = torch.cat(target_input, 1)

        cnn_input = torch.cat(
            [
                concat_source_input,
                concat_target_input
            ],
            1
        )
        x = self.initial_pool(cnn_input)

        x = self.running_mean_and_var(x)
        x = self.backbone(x)
        x = self.compression(x)
        x = self.visual_fc(x)

        return x