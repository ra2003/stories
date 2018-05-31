import sys

from .exceptions import FailureError


class story(object):

    def __init__(self, f):
        self.f = f

    def __get__(self, obj, cls):
        return StoryWrapper(obj, cls, self.f)


def argument(name):

    def decorator(f):
        if not hasattr(f, "arguments"):
            f.arguments = []
        f.arguments.insert(0, name)
        return f

    return decorator


class Result(object):

    def __init__(self, value=None):
        self.value = value

    def __repr__(self):
        return self.__class__.__name__ + "(" + repr(self.value) + ")"


class Success(object):

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __repr__(self):
        return self.__class__.__name__ + namespace_representation(self.kwargs)


class Failure(object):

    def __init__(self, reason=None):
        # TODO: Show reason in Failure repr.
        #
        # TODO: Show reason in Proxy repr.
        #
        # TODO: Add failed_because method to the FailureSummary and
        # SuccessSummary.
        self.reason = reason

    def __repr__(self):
        return self.__class__.__name__ + "()"


class Skip(object):

    def __repr__(self):
        return self.__class__.__name__ + "()"


class Undefined(object):  # TODO: Rename to Marker.
    pass


undefined = Undefined()


class StoryWrapper(object):

    def __init__(self, obj, cls, f):
        self.obj = obj
        self.cls = cls
        self.f = f

    def __call__(self, *args, **kwargs):
        return tell_the_story(self.obj, self.f, args, kwargs)

    def run(self, *args, **kwargs):
        return run_the_story(self.obj, self.f, args, kwargs)

    def __repr__(self):
        return story_representation(self)


def tell_the_story(obj, f, args, kwargs):

    ctx = Context(validate_arguments(f, args, kwargs))
    the_story = []
    f(Collector(obj, the_story, f))
    skipped = undefined
    history = ["Proxy(" + obj.__class__.__name__ + "." + f.__name__ + "):"]
    indent_level = 1

    for self, method, of in the_story:

        if skipped is not undefined:
            if method is end_of_story and skipped is of:
                skipped = undefined
            continue

        history.append("  " * indent_level + method.__name__)
        result = method(make_proxy(self, ctx, history))

        restype = type(result)
        assert restype in (Result, Success, Failure, Skip, Undefined)

        if restype is Failure:
            if result.reason:
                history[-1] = history[-1] + " (failed: " + repr(result.reason) + ")"
            else:
                history[-1] = history[-1] + " (failed)"
            raise FailureError(result.reason)

        if restype is Result:
            history[-1] = history[-1] + " (returned: " + repr(result.value) + ")"
            return result.value

        if restype is Skip:
            history[-1] = history[-1] + " (skipped)"
            skipped = of
            # Substory will be skipped.
            indent_level -= 1
            continue

        if restype is Undefined:
            history.pop()
            if result is valid_arguments:
                # The beginning of substory.
                history.append("  " * indent_level + method.method_name)
                indent_level += 1
            else:
                # The end of substory.
                indent_level -= 1
            continue

        assert not set(ctx.ns) & set(result.kwargs)
        ctx.ns.update(result.kwargs)
        line = "Set by %s.%s" % (self.__class__.__name__, method.__name__)
        ctx.lines.extend([(key, line) for key in result.kwargs])


def run_the_story(obj, f, args, kwargs):

    ctx = Context(validate_arguments(f, args, kwargs))
    the_story = []
    f(Collector(obj, the_story, f))
    skipped = undefined
    history = ["Proxy(" + obj.__class__.__name__ + "." + f.__name__ + "):"]
    indent_level = 1

    for self, method, of in the_story:

        if skipped is not undefined:
            if method is end_of_story and skipped is of:
                skipped = undefined
            continue

        history.append("  " * indent_level + method.__name__)
        result = method(make_proxy(self, ctx, history))

        restype = type(result)
        assert restype in (Result, Success, Failure, Skip, Undefined)

        if restype is Failure:
            if result.reason:
                history[-1] = history[-1] + " (failed: " + repr(result.reason) + ")"
            else:
                history[-1] = history[-1] + " (failed)"
            return FailureSummary(ctx, method.__name__, result.reason)

        if restype is Result:
            history[-1] = history[-1] + " (returned: " + repr(result.value) + ")"
            return SuccessSummary(result.value)

        if restype is Skip:
            history[-1] = history[-1] + " (skipped)"
            skipped = of
            # Substory will be skipped.
            indent_level -= 1
            continue

        if restype is Undefined:
            history.pop()
            if result is valid_arguments:
                # The beginning of substory.
                history.append("  " * indent_level + method.method_name)
                indent_level += 1
            else:
                # The end of substory.
                indent_level -= 1
            continue

        assert not set(ctx.ns) & set(result.kwargs)
        ctx.ns.update(result.kwargs)
        line = "Set by %s.%s" % (self.__class__.__name__, method.__name__)
        ctx.lines.extend([(key, line) for key in result.kwargs])

    return SuccessSummary(None)


def validate_arguments(f, args, kwargs):

    assert not (args and kwargs)
    arguments = getattr(f, "arguments", [])

    if args:
        assert len(arguments) == len(args)
        return {k: v for k, v in zip(arguments, args)}

    assert set(arguments) == set(kwargs)
    return kwargs


class Context(object):

    def __init__(self, ns):
        self.ns = ns
        self.lines = [(key, "Story argument") for key in ns]

    def __getattr__(self, name):
        return self.ns[name]

    def __eq__(self, other):
        return self.ns == other

    def __repr__(self):
        if not self.lines:
            return self.__class__.__name__ + "()"
        assignments = [
            ("%s = %s" % (key, repr(self.ns[key])), line) for key, line in self.lines
        ]
        longest = max(map(lambda x: len(x[0]), assignments))
        return "\n".join(
            [self.__class__.__name__ + ":"]
            + [
                "    %s  # %s" % (assignment.ljust(longest), line)
                for assignment, line in assignments
            ]
        )

    def __dir__(self):
        parent = set(dir(undefined))
        current = set(self.__dict__) - {"ns", "lines", "__position__"}
        scope = set(self.ns)
        attributes = sorted(parent | current | scope)
        return attributes


class Collector(object):

    def __init__(self, obj, method_calls, of):
        self.obj = obj
        self.method_calls = method_calls
        self.of = of

    def __getattr__(self, name):

        attribute = getattr(self.obj.__class__, name, undefined)

        if attribute is not undefined:
            if is_story(attribute):
                collect_substory(attribute.f, self.obj, self.method_calls, name)
                return lambda: None

            self.method_calls.append((self.obj, attribute, self.of))
            return lambda: None

        attribute = getattr(self.obj, name)
        assert is_story(attribute)
        history_name = (
            name
            + " ("
            + attribute.obj.__class__.__name__
            + "."
            + attribute.f.__name__
            + ")"
        )
        collect_substory(attribute.f, attribute.obj, self.method_calls, history_name)
        return lambda: None


PY3 = sys.version_info[0] >= 3


if PY3:

    def make_proxy(obj, ctx, history):
        return Proxy(obj, ctx, history)


else:

    def make_proxy(obj, ctx, history):

        class ObjectProxy(Proxy, obj.__class__):
            pass

        return ObjectProxy(obj, ctx, history)


class Proxy(object):

    def __init__(self, obj, ctx, history):
        self.obj = obj
        self.ctx = ctx
        self.history = history

    def __getattr__(self, name):
        return getattr(self.obj, name)

    def __repr__(self):
        return "\n".join(self.history)


class FailureSummary(object):

    def __init__(self, ctx, failed_method, reason):
        self.is_success = False
        self.is_failure = True
        self.ctx = ctx
        self.failed_method = failed_method
        self.reason = reason

    def failed_on(self, method_name):
        return method_name == self.failed_method

    def failed_because(self, reason):
        return reason == self.reason

    @property
    def value(self):
        raise AssertionError


class SuccessSummary(object):

    def __init__(self, value):
        self.is_success = True
        self.is_failure = False
        self.value = value

    def failed_on(self, method_name):
        return False

    def failed_because(self, reason):
        return False


def is_story(attribute):
    return callable(attribute) and type(attribute) is StoryWrapper


valid_arguments = Undefined()


def collect_substory(f, obj, method_calls, history_name):

    arguments = getattr(f, "arguments", [])

    def validate_substory_arguments(self):
        assert set(arguments) <= set(self.ctx.ns)
        return valid_arguments

    validate_substory_arguments.method_name = history_name

    method_calls.append((obj, validate_substory_arguments, f))
    f(Collector(obj, method_calls, f))
    method_calls.append((obj, end_of_story, f))


def end_of_story(self):
    return undefined


def namespace_representation(ns):
    return "(" + ", ".join([k + "=" + repr(v) for k, v in ns.items()]) + ")"


def story_representation(wrapper):

    lines = [wrapper.cls.__name__ + "." + wrapper.f.__name__]
    represent = Represent(wrapper, lines, 1)
    wrapper.f(represent)
    if not represent.touched:
        lines.append("  <empty>")
    return "\n".join(lines)


class Represent(object):

    def __init__(self, wrapper, lines, level):
        self.wrapper = wrapper
        self.lines = lines
        self.level = level
        self.touched = False

    def __getattr__(self, name):
        self.touched = True
        attribute = getattr(self.wrapper.obj.__class__, name, undefined)
        if attribute is not undefined and is_story(attribute):
            self.lines.append("  " * self.level + name)
            represent = Represent(self.wrapper, self.lines, self.level + 1)
            attribute.f(represent)
            if not represent.touched:
                self.lines.append("  " * (self.level + 1) + "<empty>")
            return lambda: None

        attribute = getattr(self.wrapper.obj, name, undefined)
        if attribute is not undefined and is_story(attribute):
            self.lines.append(
                "  " * self.level
                + name
                + " ("
                + attribute.cls.__name__
                + "."
                + attribute.f.__name__
                + ")"
            )
            represent = Represent(attribute, self.lines, self.level + 1)
            attribute.f(represent)
            if not represent.touched:
                self.lines.append("  " * (self.level + 1) + "<empty>")
            return lambda: None

        self.lines.append("  " * self.level + name)
        return lambda: None
