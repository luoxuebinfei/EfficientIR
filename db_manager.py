import sqlite3


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.create_table()

    def create_table(self):
        """创建表"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS resource (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    mangnetUrl TEXT,
                    webUrl TEXT,
                    note TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS path (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    path TEXT,
                    resource_id INTEGER
                )""")

    def insert_data(self, data: tuple, insert_resource=True) -> tuple:
        with sqlite3.connect(self.db_path) as conn:
            try:
                c = conn.cursor()
                if insert_resource:
                    # 插入resource表
                    c.execute("INSERT INTO resource ('title', 'mangnetUrl', 'webUrl', 'note') VALUES (?, ?, ?, ?)", data[:-1])
                    resource_id = c.lastrowid
                    # 插入path表
                    c.execute("INSERT INTO path ('title', 'path', 'resource_id') VALUES (?, ?, ?)", (data[0], data[-1], resource_id))
                    path_id = c.lastrowid
                else:
                    # 插入path表
                    c.execute("INSERT INTO path ('title', 'path', 'resource_id') VALUES (?, ?, ?)", data)
                    resource_id = data[-1]
                    path_id = c.lastrowid

                # 提交事务
                conn.commit()
                return resource_id, path_id
            except sqlite3.Error as e:
                # 发生错误时回滚事务
                conn.rollback()
                raise e

    def query_data(self, table_name, condition=None) -> list:
        """查询数据

        Args:
            table_name (str): 表的名字
            condition (_type_, optional): 查询的条件

        Returns:
            list: 查询的结果
        """
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            if condition:
                c.execute(f"SELECT * FROM {table_name} WHERE {condition}")
            else:
                c.execute(f"SELECT * FROM {table_name}")
            return c.fetchall()

    def update_data(self,table_name, data, condition):
        """更新数据

        Args:
            table_name (str): 表的名字
            data (str): 更新的数据
            condition (str): 更新的条件
        """
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(f"UPDATE {table_name} SET {data} WHERE {condition}")
            conn.commit()

