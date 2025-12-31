from setuptools import find_packages, setup

REQUIRES = []

setup(
    name='RequestChain',
    description='a lightweight blockchain for handling general messaging',
    author_email='chris.is.rad@pm.me',
    author='Christopher Walsh MLIS',
    license='BSD-3-Clause',
    version='0.0.2',
    packages=find_packages(),
    install_requires=REQUIRES,
    entry_points={
        'console_scripts': [
            'reqchain = net.main:main'
        ]
    },
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3"
    ]
)