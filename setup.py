from setuptools import setup, find_packages

setup(
	name='multirunner',
	version='0.0.1',
	packages=find_packages(exclude=['tests']),
	package_data={'multirunner.handlers': ['*.*']},
	include_package_data=True
)