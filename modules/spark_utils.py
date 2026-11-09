import os
import sys

from pyspark.sql import SparkSession

import config




def create_session(app_name):
    os.environ["PYSPARK_PYTHON"] = sys.executable      # executors use the same Python (venv) as the driver

    # one session per run, master and memory are set in config
    builder = SparkSession.builder.master(config.SPARK_MASTER).appName(app_name)
    builder = builder.config("spark.driver.memory", config.SPARK_DRIVER_MEMORY)
    spark = builder.getOrCreate()

    spark.sparkContext.setLogLevel("WARN")      # hide INFO logs, show only warnings and errors
    return spark
