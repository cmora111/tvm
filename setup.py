import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="tvm",
    version="0.0.1",
    description="Virtual Macropad",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/cmora111/tvm",
    author="Carlos Mora",
    author_email="mora@spectrix.com",
    license="GNU",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications",
        "Programming Language :: Python :: 3.8",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Topic :: Terminals :: Terminal Emulators/X Terminals",
        "Topic :: Utilities",
    ],
    packages=["src", "docs"],
    include_package_data=False,
    install_requires=[
        "python_version == 3.8",
        "python-libxdo @ git+https://git@github.coom/rshk/python-libxdo"
    ]
    )
