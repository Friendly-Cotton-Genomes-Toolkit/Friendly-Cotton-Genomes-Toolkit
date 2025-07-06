# setup.py

from setuptools import setup, find_packages
from babel.messages.frontend import compile_catalog, extract_messages, init_catalog, update_catalog
import os

# 定义应用名称和版本，可以从您的 __init__.py 或其他地方导入
APP_NAME = "Friendly Cotton Genomes Toolkit"
VERSION = "1.0.0"


def get_locale_dir():
    """获取 locales 目录的路径"""
    return os.path.join(APP_NAME, 'locales')


setup(
    name=APP_NAME,
    version=VERSION,
    author="Your Name",  # 请替换为您的名字
    author_email="your.email@example.com",  # 请替换为您的邮箱
    description="A modern toolkit for cotton genomics research.",
    long_description=open('README.md', 'r', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    url="https://github.com/PureAmaya/Friendly-Cotton-Genomes-Toolkit",  # 您的项目URL

    # 自动查找项目中的所有包
    packages=find_packages(),

    # 包含非代码文件，这是【关键】，确保 .mo 文件被打包
    include_package_data=True,
    package_data={
        # 告诉 setuptools 包含所有 locales 目录下的 .mo 文件
        APP_NAME: ['locales/*/LC_MESSAGES/*.mo'],
    },

    # 定义依赖项
    install_requires=[
        "click",
        "pandas",
        "pyyaml",
        # ... 在此列出您项目运行所需的所有其他依赖 ...
    ],

    # 设置命令行入口点
    entry_points={
        'console_scripts': [
            'fcgt = cotton_toolkit.cli:cli',
        ],
    },

    # ---------------- Babel 多语言配置 ----------------

    # 定义 setup.py 可用的命令
    cmdclass={
        'compile_catalog': compile_catalog,
        'extract_messages': extract_messages,
        'init_catalog': init_catalog,
        'update_catalog': update_catalog,
    },

    # 定义文本提取规则
    message_extractors={
        APP_NAME: [
            ('**.py', 'python', None),
        ],
    },

    # 定义 setup 期间的依赖，Babel 是必需的
    setup_requires=['Babel'],

    # ---------------- 其他元数据 ----------------

    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Natural Language :: Chinese (Simplified)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
    python_requires='>=3.9',
)



# python setup.py extract_messages -o cotton_toolkit/cotton_toolkit.pot