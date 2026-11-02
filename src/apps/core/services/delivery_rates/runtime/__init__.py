"""The delivery-rate limiter: admission, provider feedback, daily budgets, breakers and provider limit discovery,
applied to ``DeliveryRateState`` in short transactions. No lock is ever held across a provider call or a sleep.
"""
