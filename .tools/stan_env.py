"""Import before cmdstanpy to use a conda-forge CmdStan toolchain (default ~/.mm/envs/cs; override with CMDSTAN_ENV)."""
import os

E = os.environ.get("CMDSTAN_ENV", os.path.join(os.path.expanduser("~"), ".mm", "envs", "cs"))
os.environ["PATH"] = os.pathsep.join(
    [E + r"\Library\bin", E + r"\Library\usr\bin", E + r"\Library\mingw-w64\bin", os.environ["PATH"]])
os.environ["CMDSTAN"] = E + r"\Library\bin\cmdstan"
os.environ["MAKE"] = "make"
os.environ["CXX"] = "x86_64-w64-mingw32-g++"
os.environ["CC"] = "x86_64-w64-mingw32-gcc"
os.environ["AR"] = "x86_64-w64-mingw32-ar"
