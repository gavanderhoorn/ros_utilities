# Copyright (c) 2023 Boston Dynamics AI Institute Inc.  All rights reserved.
import time
from typing import Iterable, Optional, Tuple

import pytest
import rclpy
from geometry_msgs.msg import Quaternion, Transform, TransformStamped, Vector3
from rclpy.duration import Duration
from rclpy.time import Time
from tf2_ros import ExtrapolationException, LookupException, TransformBroadcaster

from bdai_ros2_wrappers.node import Node
from bdai_ros2_wrappers.process import ROSAwareScope
from bdai_ros2_wrappers.tf_listener_wrapper import TFListenerWrapper

ROBOT = "test_robot"
CAMERA = "camera_1"
FRAME_ID = f"{ROBOT}/body"
CHILD_FRAME_ID = f"{ROBOT}/{CAMERA}"


def equal_transform(a: Transform, b: Transform) -> bool:
    return (
        a.translation.x == b.translation.x
        and a.translation.y == b.translation.y
        and a.translation.z == b.translation.z
        and a.rotation.w == b.rotation.w
        and a.rotation.x == b.rotation.x
        and a.rotation.y == b.rotation.y
        and a.rotation.z == a.rotation.z
    )


class MockTfPublisherNode(Node):
    def __init__(self, frame_id: str, child_frame_id: str) -> None:
        super().__init__("mock_tf_publisher")

        self._frame_id = frame_id
        self._child_frame_id = child_frame_id
        self._tf_broadcaster = TransformBroadcaster(self)

    def publish_transform(self, trans: Transform, timestamp: Optional[Time]) -> None:
        t = TransformStamped()

        if timestamp is not None:
            t.header.stamp = timestamp.to_msg()
        t.header.frame_id = self._frame_id
        t.child_frame_id = self._child_frame_id

        t.transform = trans

        self._tf_broadcaster.sendTransform(t)


@pytest.fixture
def ros() -> Iterable[ROSAwareScope]:
    rclpy.init()
    try:
        with ROSAwareScope("fixture") as scope:
            yield scope
    finally:
        rclpy.try_shutdown()


@pytest.fixture
def tf_pair(ros: ROSAwareScope) -> Iterable[Tuple[MockTfPublisherNode, TFListenerWrapper]]:
    tf_publisher = MockTfPublisherNode(FRAME_ID, CHILD_FRAME_ID)
    ros.executor.add_node(tf_publisher)
    tf_listener = TFListenerWrapper(ros.node)
    yield tf_publisher, tf_listener
    ros.executor.remove_node(tf_publisher)


def test_non_existant_transform(ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    with pytest.raises(LookupException):
        tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp)


def test_non_existant_transform_timeout(
    ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]
) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    start = time.time()
    with pytest.raises(LookupException):
        tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp, timeout=20.0)
    assert time.time() - start < 10.0


def test_existing_transform(ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    trans = Transform(translation=Vector3(x=1.0, y=2.0, z=3.0), rotation=Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    tf_publisher.publish_transform(trans, timestamp)
    time.sleep(0.2)
    t = tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp)
    assert equal_transform(t.transform, trans)


def test_future_transform_extrapolation_exception(
    ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]
) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    trans = Transform(translation=Vector3(x=1.0, y=2.0, z=3.0), rotation=Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    tf_publisher.publish_transform(trans, timestamp)
    time.sleep(0.2)
    timestamp = ros.node.get_clock().now()
    with pytest.raises(ExtrapolationException):
        tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp)


def test_future_transform_insufficient_wait(
    ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]
) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    trans = Transform(translation=Vector3(x=1.0, y=2.0, z=3.0), rotation=Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    tf_publisher.publish_transform(trans, timestamp)

    delay = 2

    def delayed_publish() -> None:
        time.sleep(delay)
        delayed_timestamp = ros.node.get_clock().now()
        tf_publisher.publish_transform(trans, delayed_timestamp)

    ros.executor.create_task(delayed_publish)

    time.sleep(0.2)
    timestamp = ros.node.get_clock().now() + Duration(seconds=delay)
    with pytest.raises(ExtrapolationException):
        tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp, timeout=0.5)


def test_future_transform_wait(ros: ROSAwareScope, tf_pair: Tuple[MockTfPublisherNode, TFListenerWrapper]) -> None:
    tf_publisher, tf_listener = tf_pair
    timestamp = ros.node.get_clock().now()
    trans = Transform(translation=Vector3(x=1.0, y=2.0, z=3.0), rotation=Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    tf_publisher.publish_transform(trans, timestamp)

    delay = 1

    def delayed_publish() -> None:
        time.sleep(delay + 0.001)
        delayed_timestamp = tf_publisher.get_clock().now()
        tf_publisher.publish_transform(trans, delayed_timestamp)

    ros.executor.create_task(delayed_publish)

    timestamp += Duration(seconds=delay)
    t = tf_listener.lookup_a_tform_b(FRAME_ID, CHILD_FRAME_ID, timestamp, wait_for_frames=True, timeout=2)
    assert equal_transform(t.transform, trans)
