import sys, json, io, time, traceback, itertools, re, os, math, base64, importlib
from collections import namedtuple
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from io import StringIO, BytesIO
import pandas as pd
import sqlite3

land = None # land module

################################nn########
# TEST FRAMEWORK
########################################

TestFunc = namedtuple("TestFunc", ["fn", "points"])
tests = []

prog_name = "main.py"

# if @test(...) decorator is before a function, add that function to test_fucns
def test(points):
    def add_test(fn):
        tests.append(TestFunc(fn, points))
        return fn
    return add_test

# override print so can also capture output for results.json
print_buf = None
orig_print = print
def print(*args, **kwargs):
    orig_print(*args, **kwargs)
    if print_buf != None:
        orig_print(*args, **kwargs, file=print_buf)

# both are simple name => val
# expected_json <- expected.json (before tests)
# actual_json -> actual.json (after tests)
#
# TIP: to generate expected.json, run the tests on a good
# implementation, then copy actual.json to expected.json
expected_json = None
actual_json = {"version": 2}

# return string (error) or None
def is_expected2(actual, name, histo_comp=False):
    global expected_json

    actual_json[name] = actual
    if expected_json == None:
        with open("expected.json") as f:
            expected_json = json.load(f)

    expected = expected_json.get(name, None)
    
    # for hist_comp, we don't care about order of the two list like
    # objects.  We just care that the two histograms are similar.
    if histo_comp:
        if actual == None or expected == None:
            return ("invalid histo_comp types: {}, {}".format(type(actual), type(expected)))
        
        if len(actual) != len(expected):
            return "expected {} points but found {} points".format(len(expected), len(actual))
        diff = 0
        actual = sorted(actual)
        expected = sorted(expected)
        for a, e in zip(actual, expected):
            diff += abs(a - e)
        diff /= len(expected)
        if diff > 0.01:
            return "average error between actual and expected was %.2f (>0.01)" % diff

    elif type(expected) != type(actual) and expected != None and actual != None:
        return "expected a {} but found {} of type {}".format(expected, actual, type(actual))

    elif expected != actual:
        return "expected {} but found {}".format(expected, actual)

    return None

# wraps is_expected, just adds name to error messages
def is_expected(actual, name, histo_comp=False):
    err = is_expected2(actual, name, histo_comp)
    if err:
        return f"{err} [BAD {name}]"
    return None

# execute every function with @test decorator; save results to results.json
def run_all_tests(mod_name):
    global land, print_buf
    print("Running tests...")

    land = importlib.import_module(mod_name)

    results = {'score':0, 'tests': [], 'lint': [], "date":datetime.now().strftime("%m/%d/%Y")}
    total_points = 0
    total_possible = 0

    t0 = time.time()
    for t in tests:
        print_buf = StringIO() # trace prints
        print("="*40)
        print("TEST {} ({} points possible)".format(t.fn.__name__, t.points))
        try:
            points = t.fn()
        except Exception as e:
            print(traceback.format_exc())
            points = 0
        if points > t.points:
            raise Exception("got {} points on {} but expected at most {}".format(points, t.fn.__name__, t.points))
        total_points += points
        total_possible += t.points
        row = {"test": t.fn.__name__, "points": points, "possible": t.points}
        if points != t.points:
            row["log"] = print_buf.getvalue().split("\n")
        results["tests"].append(row)
        print_buf = None # stop tracing prints
        print("TEST RESULT: {} of {} points".format(points, t.points))

    print("="*40)
    print("Earned {} of {} points across all tests".format(total_points, total_possible))
    results["score"] = round(100.0 * total_points / total_possible, 1)

    # how long did it take?
    t1 = time.time()
    max_sec = 240
    sec = t1-t0
    if sec > max_sec/2:
        print("WARNING!  Tests took", sec, "seconds")
        print("Maximum is ", sec, "seconds")
        print("We recommend keeping runtime under half the maximum as a buffer.")
        print("Variability may cause it to run slower for us than you.")

    results["latency"] = sec

    # output results
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open("actual.json", "w", encoding="utf-8") as f:
        json.dump(actual_json, f, indent=2)

    print("="*40)
    print("SCORE: %.1f%% (details in results.json)" % results["score"])

    # does tester.py version match expected.json version?
    if actual_json["version"] != expected_json["version"]:
        print("#"*80)
        print("#"*80)
        print("#")
        if actual_json["version"] > expected_json["version"]:
            print("# WARING! There's a newer version of expected.json, please re-download")
        else:
            print("# WARING! There's a newer version of tester.py, please re-download")
        print("#")
        print("#"*80)
        print("#"*80)

########################################
# TESTS
########################################

@test(points=10)
def conn_cleanup():
    points = 0

    c1 = land.open("images")
    err = is_expected(type(c1).__name__, "conn_cleanup:type-name")
    if err:
        print(err)
        return 0

    points += 2

    try:
        c1.db.execute("select * from sqlite_master")
        points += 2
    except sqlite3.ProgrammingError:
        print("1 - db connection isn't open for an open land.Connection")

    c1.close()
    try:
        c1.db.execute("select * from sqlite_master")
        print("c1.close() didn't close underlying db")
    except sqlite3.ProgrammingError:
        points += 2

    if not (hasattr(c1, "__enter__") and hasattr(c1, "__exit__")):
        print("Connection is not a context manager (missing special functions)")
        return points

    with land.open("images") as c2:
        try:
            c2.db.execute("select * from sqlite_master")
            points += 2
        except sqlite3.ProgrammingError:
            print("2 - db connection isn't open for an open land.Connection")

    try:
        c2.db.execute("select * from sqlite_master")
        print("underlying db not closed after context manager exit")
    except sqlite3.ProgrammingError:
        points += 2

    return points

@test(points=5)
def list_images():
    points = 0
    with land.open("images") as c:
        imgs = c.list_images()
        points += 2

        err = is_expected(imgs, "list_images")
        if err:
            print(err)
        else:
            points += 3
    return points

@test(points=5)
def image_year():
    errs = []
    with land.open("images") as c:
        for i in range(170):
            img = "area%d.npy" % i
            err = is_expected(c.image_year(img), "image_year:%d"%i)
            if err:
                errs.append(err)
    if errs:
        print(errs[0])
        return 1
    return 5

@test(points=5)
def image_name():
    errs = []
    with land.open("images") as c:
        for i in range(170):
            img = "area%d.npy" % i
            err = is_expected(c.image_name(img), "image_name:%d"%i)
            if err:
                errs.append(err)
    if errs:
        print(errs[0])
        return 1
    return 5

@test(points=5)
def image_load():
    errs = []
    with land.open("images") as c:
        for i in range(170):
            img = "area%d.npy" % i
            matrix = c.image_load(img)
            shape = [int(x) for x in matrix.shape]
            err = is_expected(shape, "image_load:shape:%d"%i)
            if err:
                errs.append(err)
            else:
                point_sample = [int(x) for x in matrix[::150,::150].reshape(-1)]
                err = is_expected(point_sample, "image_load:points:%d"%i)
                if err:
                    errs.append(err)
    if errs:
        print(errs[0])
        return 1
    return 5

@test(points=70)
def other_tests():
    print("not released yet, we'll announce when they are...")
    return 0

########################################
# RUNNER
########################################

def main():
    # import land.py (or other, if specified)
    mod_name = "land"
    if len(sys.argv) > 2:
        print("Usage: python3 test.py [mod_name]")
        sys.exit(1)
    elif len(sys.argv) == 2:
        mod_name = sys.argv[1]

    run_all_tests(mod_name)

if __name__ == "__main__":
    main()