# Third Party
import pytest

# Patterns
from patterns.state import StateError, StateRegistry, add_state

state = StateRegistry()


class ArticleState:
    def __repr__(self):
        # TODO(BK): use dataclass or so in a next step
        return f'{self.__class__.__name__}'


@state.register(initial=True)
class Demanded(ArticleState):
    @state.transition(to='Ordered')
    def order(self, cost: float) -> 'Ordered':
        return Ordered(cost)


@state.register(attributes=['cost'])
class Ordered(ArticleState):
    # TODO(BK): should be shared for all but demanded
    def __init__(self, cost: float):
        self.cost = cost

    @state.transition(to='InStock')
    def arrived_at_stock(self, stock_location: int) -> 'InStock':
        return InStock(cost=self.cost, stock_location=stock_location)


@state.register(attributes=['stock_location'])
class InStock(ArticleState):
    def __init__(self, cost: float, stock_location: int):
        self.cost = cost
        self.stock_location = stock_location

    @state.transition(to='OnDispatch')
    def ship(self, address: str, price_sold: float) -> 'OnDispatch':
        return OnDispatch(
            cost=self.cost, shipping_address=address, price_sold=price_sold
        )


class SoldStateMixin:
    def __init__(self, cost: float, price_sold: float):
        self.cost = cost
        self.price_sold = price_sold


@state.register(attributes=['shipping_address'])
class OnDispatch(SoldStateMixin, ArticleState):
    def __init__(self, *args, shipping_address: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.shipping_address = shipping_address

    @state.transition(to='Sold')
    def arrived_at_customer(self):
        return Sold(cost=self.cost, price_sold=self.price_sold)


@state.register
class Sold(SoldStateMixin, ArticleState):
    @state.property_
    def margin(self) -> float:
        return self.price_sold - self.cost


@add_state(state)
class Article:
    # TODO(BK): report collisions in attributes and so on!
    number: int
    category: str
    initial_price: float


def test():
    article = Article()  # gets created with the default state
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
        match='Article object in state OnDispatch does not support calling stock_location.',
    ):
        _ = article.stock_location

    article.arrived_at_customer()
    assert isinstance(article.state, Sold)
    assert round(article.margin, 4) == round(1.4000, 4)
