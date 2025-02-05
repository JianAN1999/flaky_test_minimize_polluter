import linecache
import ast
import os
import time
import hashlib
import shutil
from io import StringIO
import io
import uuid
from ipflakies.utils import *
from ipflakies.unparse import Unparser


import pytest
import tempfile
import json
import importlib.util

def create_temp_file_in_dir(polluter_path, original_dir):
    """
    Create a temporary file and copy the original polluter's content into it for later restoration
    """
    if not os.path.exists(original_dir):
        os.makedirs(original_dir)

    temp_path = os.path.join(original_dir, os.path.basename(polluter_path).replace(".py", "_temp.py"))
    
    with open(polluter_path, 'r') as polluter_file:
        content = polluter_file.read()
    
    with open(temp_path, 'w') as temp_file:
        temp_file.write(content)
    
    print(f"Temporary file created: {temp_path}")
    return temp_path

def find_function_in_ast(temp_tree, function_name):
    """
    Get polluter() node from the AST tree
    :param temp_tree: The AST tree of the temporary file  
    :param function_name: The name of the polluter function  
    :return: The AST node of the polluter function  
    """
    for node in ast.walk(temp_tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise ValueError(f"Polluter function '{function_name}' not found.")

def node_to_code(node):
    """
    Converts an AST node to a code string
    """
    output = StringIO()
    Unparser(node, output)
    output.seek(0)
    return output.read()

def minimize_polluter_function(polluter_test, victim, polluter_dir, task_kind):
    """
    Get the minimized Polluter code and generate a file to store it
    """
    polluter_path = polluter_test['module']
    polluter_class_name = polluter_test['class']
    polluter_function_name = polluter_test['function']
    polluter_para = polluter_test['para']

    # Step 1: Parse polluter file into an AST tree
    with open(polluter_path, 'r') as f:
        original_file_content = f.read()  # Backup the original file content
        polluter_tree = ast.parse(original_file_content)

    
    # Step 2: Find polluter function node
    polluter_node = find_function_in_ast(polluter_tree, polluter_function_name)

    # Step 3: Backup the original polluter function body
    original_body = polluter_node.body[:]
    
    # Step 4: Prepare for minimization
    if not os.path.exists(polluter_dir):
        os.makedirs(polluter_dir)

    n = 2  # Initial subset size
    roundnum = 0  # Round counter


    while len(original_body) >= 2:
        print(f"Original Body Length: {len(original_body)}")
        subset_length = max(1, int(len(original_body) // n))  # Ensure subset length is at least 1
        is_found = False

        for i in range(0, len(original_body), subset_length):
            # Create a temporary subset of the polluter body
            temp_body = original_body[:i] + original_body[i + subset_length:]
            polluter_node.body = temp_body

            # Write the modified tree back to the original file
            with open(polluter_path, 'w') as f:
                f.write(node_to_code(polluter_tree))
            
            print(f"Testing Body Subset (Round {roundnum}, Subset Length {subset_length}): {temp_body}")

            # Generate pytest arguments
            if polluter_test['class']:
                temp_polluter = f"{polluter_path}::{polluter_test['class']}::{polluter_test['function']}"
            else:
                temp_polluter = f"{polluter_path}::{polluter_test['function']}"

            if polluter_test['para']:
                temp_polluter += polluter_test["para"]

            # Verify the subset
            is_prefunc_passed = verify([temp_polluter], "passed")
            print("is_prefunction_passed: \n", is_prefunc_passed)

            if task_kind == "victim":
                is_result_matched = verify([temp_polluter, victim], "failed")
            elif task_kind == "brittle":
                is_result_matched = verify([temp_polluter, victim], "passed")
            print("is_result_matched: \n", is_result_matched)

            # If valid, update the original body
            if is_prefunc_passed and is_result_matched:
                print(f"Valid Subset Found: {temp_body}")
                original_body = temp_body  # Update to the minimal subset
                is_found = True
                break

        if not is_found:
            n = min((n * 2), len(original_body))
            if n == len(original_body):
                break
    
    # Step 5: Analyze global variables in the minimized polluter
    polluter_node.body = original_body  # Use the final minimized body for analysis
    minimized_code = node_to_code(polluter_tree)
    minimized_tree = ast.parse(minimized_code)

    # Step 6: Restore the original file content
    with open(polluter_path, 'w') as f:
        f.write(original_file_content)
    print(f"Original file restored: {polluter_path}")

    # Step 7: Write the minimized code to a new file
    minimized_file_path = os.path.join(polluter_dir, f"{polluter_function_name}_minimized.py")
    with open(minimized_file_path, 'w') as f_minimized:
        polluter_node.body = original_body
        f_minimized.write(node_to_code(polluter_tree))
    print(f"Minimized Polluter File saved to: {minimized_file_path}")


def node_to_code(tree):
    """
    Convert an AST tree to a code string using a custom Unparser class.
    """
    output = StringIO()
    Unparser(tree, output)
    output.seek(0)
    return output.read()


def generate_minimized_polluter(polluter, victim, SAVE_DIR_MD5):
    md5 = hashlib.md5((polluter).encode(encoding='UTF-8')).hexdigest()[:8]

    victim_test = split_test(victim, rmpara=True)
    polluter_test = split_test(polluter, rmpara=True)

    # get the path
    victim_path = victim_test["module"]
    polluter_path = polluter_test["module"]
    polluter_dir, _ = os.path.split(polluter_path)

    print("polluter:", polluter)
    print("polluter_test: ", split_test(polluter, rmpara=True))

    if verify([victim], "failed") and verify([polluter, victim], "passed"):
        task_kind = "brittle"
    else:
        task_kind = "victim"
    
    is_result_matched = verify([polluter, victim], "failed")
    print("is_result_matched: \n", is_result_matched)
    
    print("Task Kind is: ", task_kind)
    print("Starting minimization process...")
    
    # call minimize_polluter_function() to get the minimized polluter file
    minimize_polluter_function(
        polluter_test=polluter_test,
        victim=victim,
        polluter_dir=polluter_dir,
        task_kind=task_kind
    )
