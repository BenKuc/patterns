# Standard Library
from typing import Optional

# Third Party
import pytest

# Patterns
from patterns.state import StateDefinition, StateError, state_transition


class ArticleState(StateDefinition, state_cls_type='definition'):
    cost: str
    stock_location: int
    price_sold: float
    margin: float

    @state_transition(to='Ordered')  # transitions must have 'to' as a return-type
    def order(self, cost: float) -> 'Ordered':
        ...

    @state_transition(to='InStock')
    def arrived_at_stock(self, stock_location: int) -> 'InStock':
        ...

    @state_transition(to='OnDispatch')
    def ship(self, address: str, price_sold: float) -> 'OnDispatch':
        ...

    @state_transition(to='Sold')
    def arrived_at_customer(self):
        ...


class Demanded(ArticleState, state_cls_type='state'):
    def order(self, cost: float) -> 'Ordered':
        return Ordered(cost)


class CostMixin:
    def __init__(self, cost: float):
        self.cost = cost


class Ordered(CostMixin, ArticleState, state_cls_type='state'):
    def arrived_at_stock(self, stock_location: int) -> 'InStock':
        return InStock(cost=self.cost, stock_location=stock_location)


class InStock(CostMixin, ArticleState, state_cls_type='state'):
    def __init__(self, cost: float, stock_location: int):
        super().__init__(cost)
        self.stock_location = stock_location

    def ship(self, address: str, price_sold: float) -> 'OnDispatch':
        return OnDispatch(
            cost=self.cost, shipping_address=address, price_sold=price_sold
        )


class SoldStateMixin(CostMixin):
    def __init__(self, cost: float, price_sold: float):
        super().__init__(cost)
        self.price_sold = price_sold


class OnDispatch(SoldStateMixin, ArticleState, state_cls_type='state'):
    def __init__(self, *args, shipping_address: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.shipping_address = shipping_address

    def arrived_at_customer(self):
        return Sold(cost=self.cost, price_sold=self.price_sold)


class Sold(SoldStateMixin, ArticleState, state_cls_type='state'):
    @property
    def margin(self) -> float:
        return self.price_sold - self.cost


class Article(ArticleState, state_cls_type='holder', default_state_cls=Demanded):
    state: ArticleState

    def __init__(
        self,
        number: int,
        category: str,
        initial_price: float,
        state: Optional[ArticleState] = None,
    ):
        self.number = number
        self.category = category
        self.initial_price = initial_price
        self.state = state or Demanded()


def test():
    article = Article(number=1, category='shoes', initial_price=44.99)

    assert isinstance(article.state, Demanded)

    article.order(cost=3.59)
    assert isinstance(article.state, Ordered)
    assert article.cost == 3.59

    article.arrived_at_stock(stock_location=331)
    assert isinstance(article.state, InStock)

    article.ship(address='...', price_sold=4.99)
    assert isinstance(article.state, OnDispatch)

    with pytest.raises(
        StateError,
        match='Member stock_location is not available on class Article in state OnDispatch.',
    ):
        _ = article.stock_location

    article.arrived_at_customer()
    assert isinstance(article.state, Sold)
    assert round(article.margin, 4) == round(1.4000, 4)
