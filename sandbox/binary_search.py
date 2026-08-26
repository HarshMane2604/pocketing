def binary_search(arr, target):
    """
    Perform binary search on a sorted array.
    
    Args:
        arr: A sorted list/array (ascending order)
        target: The value to search for
    
    Returns:
        Index of the target if found, -1 otherwise
    """
    left = 0
    right = len(arr) - 1
    
    while left <= right:
        mid = (left + right) // 2
        
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    
    return -1


def binary_search_recursion(arr, target, left=0, right=None):
    """
    Recursive implementation of binary search.
    
    Args:
        arr: A sorted list/array (ascending order)
        target: The value to search for
        left: Left boundary (default 0)
        right: Right boundary (default end of array)
    
    Returns:
        Index of the target if found, -1 otherwise
    """
    if right is None:
        right = len(arr) - 1
    
    if left > right:
        return -1
    
    mid = (left + right) // 2
    
    if arr[mid] == target:
        return mid
    elif arr[mid] < target:
        return binary_search_recursion(arr, target, mid + 1, right)
    else:
        return binary_search_recursion(arr, target, left, mid - 1)


def binary_search_ternary(arr, target):
    """
    Ternary (trisection) search implementation.
    
    Args:
        arr: A sorted list/array (ascending order)
        target: The value to search for
    
    Returns:
        Index of the target if found, -1 otherwise
    """
    left = 0
    right = len(arr) - 1
    
    while left < right:
        third = (left + right) // 3
        
        if arr[third] == target:
            return third
        elif arr[third] < target and arr[right] >= target:
            left = third
        else:
            right = third
    
    return -1


def binary_search_with_count(arr, target):
    """
    Binary search that returns both index and count of occurrences.
    
    Args:
        arr: A sorted list/array (ascending order)
        target: The value to search for
    
    Returns:
        Tuple of (index, count) or (-1, 0) if not found
    """
    first_pos = binary_search(arr, target)
    
    if first_pos == -1:
        return (-1, 0)
    
    # Count occurrences by finding last position
    last_pos = binary_search_recursion(arr, target, first_pos)
    
    count = last_pos - first_pos + 1
    
    return (first_pos, count)


def print_binary_search_example():
    """Demonstrate various binary search implementations."""
    # Sample sorted array
    arr = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    
    print("Array:", arr)
    print("=" * 50)
    
    # Test cases
    test_values = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 2]
    
    for val in test_values:
        idx_iter = binary_search(arr, val)
        idx_rec = binary_search_recursion(arr, val)
        idx_ternary = binary_search_ternary(arr, val)
        pos, count = binary_search_with_count(arr, val)
        
        print(f"\nSearching for {val}:")
        print(f"  Iterative: index {idx_iter}")
        print(f"  Recursive: index {idx_rec}")
        print(f"  Ternary: index {idx_ternary}")
        if pos >= 0:
            print(f"  With count: position {pos}, occurrences: {count}")
    
    # Test with duplicate elements
    arr_with_duplicates = [1, 2, 3, 3, 3, 4, 5]
    print("\n" + "=" * 50)
    print("Array with duplicates:", arr_with_duplicates)
    for val in [1, 2, 3, 4, 5]:
        idx = binary_search(arr_with_duplicates, val)
        pos, count = binary_search_with_count(arr_with_duplicates, val)
        print(f"\nSearching for {val}: index={idx}, position={pos}, count={count}")


if __name__ == "__main__":
    print("Binary Search Implementation Demo")
    print("=" * 50)
    
    # Run demonstration
    print_binary_search_example()
