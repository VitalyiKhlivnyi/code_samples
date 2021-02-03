import uuid
import json
import requests
from django.conf import settings
from django.urls import reverse

from settings.tokens_and_passwords import ALFABANK_LOGIN, ALFABANK_PASSWORD

BASE_URL = 'https://url'
REGISTER_TWO_STAGE_ORDER = BASE_URL + 'registerPreAuth.do'
REGISTER_ONE_STAGE_ORDER = BASE_URL + 'register.do'
SUBMIT_TWO_STAGE_ORDER = BASE_URL + 'deposit.do'
CANCEL_TWO_STAGE_ORDER = BASE_URL + 'reverse.do'
GET_ORDER_STATUS = BASE_URL + 'getOrderStatusExtended.do'


class AlfaBankFlow:
    def __init__(self):
        self.register_one_stage_order_url = REGISTER_ONE_STAGE_ORDER
        self.register_two_stage_order_url = REGISTER_TWO_STAGE_ORDER
        self.submit_two_stage_order_url = SUBMIT_TWO_STAGE_ORDER
        self.cancel_two_stage_order_url = CANCEL_TWO_STAGE_ORDER
        self.get_order_status_url = GET_ORDER_STATUS
        self.alfabank_login = ALFABANK_LOGIN
        self.alfabank_password = ALFABANK_PASSWORD
        self.success_web_hook = settings.SERVER_ADDRESS + reverse('payment_success')
        self.fail_web_hook = settings.SERVER_ADDRESS + reverse('payment_fail')

    @staticmethod
    def get_order_number():
        return uuid.uuid4().hex

    def get_base_payment_data(self, product_quantity, price, description):
        """
        create order dict from product info
        :param product_quantity: number of units
        :param price: product price for unit
        :param description: short order description
        :return:
        """
        order_data = {
            "userName": self.alfabank_login,
            "password": self.alfabank_password,
            "orderNumber": self.get_order_number(),
            "amount": f"{price * product_quantity * 100}",
            "returnUrl": self.success_web_hook,
            "failUrl": self.fail_web_hook,
            "description": description
        }
        return order_data

    def create_payment_order(self, product_quantity, price, create_url, description, merchant_id):
        """
        create new order
        :param product_quantity: number of units
        :param price: product price for unit
        :param create_url: one or two stage create order url
        :param description: short order description
        :param merchant_id: seller id in bank system
        :return:
        """
        order_data = self.get_base_payment_data(product_quantity, price, description)
        if merchant_id:
            json_params = json.dumps({"merch_code": merchant_id})
            order_data['jsonParams'] = json_params
        response = requests.post(create_url, params=order_data)
        try:
            payment_info = response.json()
        except json.decoder.JSONDecodeError:
            return None, None
        if "errorCode" in payment_info:
            return None, None
        else:
            payment_id = payment_info.pop('orderId')
            return payment_id, payment_info

    def capture_payment_order(self, order_id):
        """
        capture payment by order id
        :param order_id: hex string
        :return:
        """
        querystring = {
            "userName": self.alfabank_login,
            "password": self.alfabank_password,
            "orderId": order_id,
            "amount": 0,
        }

        response = requests.post(self.submit_two_stage_order_url, params=querystring)
        payment_info = response.json()
        if "errorCode" in payment_info:
            return None
        else:
            return payment_info

    def cancel_payment_order(self, order_id):
        """
        cancel payment by order id
        :param order_id: hex string
        :return:
        """
        querystring = {
            "userName": self.alfabank_login,
            "password": self.alfabank_password,
            "orderId": order_id,
        }

        response = requests.post(self.cancel_two_stage_order_url, params=querystring)
        payment_info = response.json()
        if "errorCode" in payment_info:
            return None
        else:
            return payment_info

    def get_payment_status(self, order_id):
        """
        check payment status by order id
        :param order_id: hex string
        :return:
        """
        querystring = {
            "userName": self.alfabank_login,
            "password": self.alfabank_password,
            "orderId": order_id,
        }

        response = requests.post(self.get_order_status_url, params=querystring)
        response_dict = response.json()
        return_dict = {
            'errorCode': response_dict['errorCode'],
            'orderStatus': response_dict['orderStatus'],
            'orderNumber': response_dict['orderNumber'],
            'actionCode': response_dict['actionCode'],
            'actionCodeDescription': response_dict['actionCodeDescription'],
        }
        return return_dict
