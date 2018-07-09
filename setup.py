from setuptools import setup, find_packages

setup(
	name='multirunner',
	version='0.0.1',
	packages=find_packages(exclude=['tests']),
	package_data={'multirunner.handlers': ['*.*']},
	include_package_data=True,
	entry_points={
		'console_scripts': ['multirunner=multirunner.__main__:main']
	},
	extras_require={
		'analytics': ['psutil'],
		'yaml': ['PyYAML']
	}
)