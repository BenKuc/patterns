from patterns.singleton import Singleton, singleton


def test_simple_singleton_class():
    class MySingleton(Singleton):
        ...

    singleton_instance = MySingleton()
    singleton_instance2 = MySingleton()
    assert  singleton_instance is singleton_instance2


def test_simple_singleton_decorator():
    @singleton
    class MySingleton:
        ...

    singleton_instance = MySingleton()
    singleton_instance2 = MySingleton()
    assert singleton_instance is singleton_instance2
