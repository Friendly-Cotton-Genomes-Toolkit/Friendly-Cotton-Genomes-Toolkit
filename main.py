# main.py
# 这是应用程序的主入口文件

# 确保从 gui_app 文件中导入主应用类
from gui_app import CottonToolkitApp

def main():
    """
    主函数，用于创建并运行应用实例。
    """
    app = CottonToolkitApp()
    app.mainloop()

if __name__ == "__main__":
    # 当直接运行 main.py 时，执行 main 函数
    main()