from database import SQL_request
from flask import Blueprint, jsonify, request, abort, g, send_file
from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash
import jwt
import datetime
import logging
from mail import send_email
from middleware import setup_middleware, auth_decorator
import config
from utils import *
import io


SECRET_KEY = config.SECRET_KEY

api = Blueprint('api', __name__)


@api.route('/', methods=['GET'])
def example():
    return jsonify({"message": f"API Работает. Версия: {config.VERSION}"}), 200