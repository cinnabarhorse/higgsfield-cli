from setuptools import setup

setup(
    name='higgsfield-cli',
    version='0.1.1',
    py_modules=['hf'],
    install_requires=[
        'curl-cffi>=0.7.0',
        'click>=8.1.0',
        'rich>=13.0.0',
    ],
    entry_points={
        'console_scripts': [
            'hf=hf:cli',
        ],
    },
    author='Clawdbot',
    description='CLI tool for generating images and videos via Higgsfield.ai',
    python_requires='>=3.10',
)
