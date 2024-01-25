def log(text, *args):
    import os
    import datetime
    print(datetime.datetime.now().strftime('%H:%M:%S.%f'), text, *args)

def pp(*args):
    import pprint
    return pprint.pprint(*args)