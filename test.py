import time
from werkzeug.datastructures import MultiDict
from multiprocessing import Process
from project import wks


d = MultiDict([("a", ["5","7","8","9"])])

d.add("key", "val")

print(d)