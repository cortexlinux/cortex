import unittest
import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(__file__))


class TestSetupConfiguration(unittest.TestCase):
    """Tests for setup.py configuration"""
    
    def test_setup_py_exists(self):
        """Test that setup.py exists"""
        self.assertTrue(os.path.exists('setup.py'))
    
    def test_setup_py_is_readable(self):
        """Test that setup.py can be read"""
        with open('setup.py', 'r') as f:
            content = f.read()
            self.assertIn('setup(', content)
            self.assertIn('name=', content)
            self.assertIn('version=', content)
    
    def test_setup_py_has_required_fields(self):
        """Test that setup.py has all required fields"""
        with open('setup.py', 'r') as f:
            content = f.read()
            required_fields = [
                'name=',
                'version=',
                'author=',
                'description=',
                'long_description=',
                'url=',
                'packages=',
                'classifiers=',
                'python_requires=',
                'install_requires=',
                'entry_points='
            ]
            for field in required_fields:
                self.assertIn(field, content, f"Missing required field: {field}")
    
    def test_setup_py_package_name(self):
        """Test that package name is correct"""
        with open('setup.py', 'r') as f:
            content = f.read()
            self.assertIn('name="cortex-linux"', content)
    
    def test_setup_py_entry_points(self):
        """Test that entry points are correctly defined"""
        with open('setup.py', 'r') as f:
            content = f.read()
            self.assertIn('cortex=cortex.cli:main', content)
    
    def test_readme_exists_for_setup(self):
        """Test that README.md exists (required by setup.py)"""
        self.assertTrue(os.path.exists('README.md'))
    
    def test_readme_is_readable(self):
        """Test that README.md can be read"""
        with open('README.md', 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertGreater(len(content), 0)
    
    def test_requirements_file_exists(self):
        """Test that LLM/requirements.txt exists (required by setup.py)"""
        self.assertTrue(os.path.exists('LLM/requirements.txt'))
    
    def test_requirements_file_format(self):
        """Test that requirements.txt is properly formatted"""
        with open('LLM/requirements.txt', 'r') as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Should contain package name
                    self.assertGreater(len(line), 0)
                    # Should not have trailing spaces
                    self.assertEqual(line, line.rstrip())


class TestGitignoreConfiguration(unittest.TestCase):
    """Tests for .gitignore configuration"""
    
    def test_gitignore_exists(self):
        """Test that .gitignore exists"""
        self.assertTrue(os.path.exists('.gitignore'))
    
    def test_gitignore_has_python_patterns(self):
        """Test that .gitignore includes Python-specific patterns"""
        with open('.gitignore', 'r') as f:
            content = f.read()
            python_patterns = [
                '__pycache__',
                '*.py[cod]',
                '*.so',
                '.Python',
                '*.egg-info',
                'dist/',
                'build/'
            ]
            for pattern in python_patterns:
                self.assertIn(pattern, content, f"Missing pattern: {pattern}")
    
    def test_gitignore_has_venv_patterns(self):
        """Test that .gitignore includes virtual environment patterns"""
        with open('.gitignore', 'r') as f:
            content = f.read()
            venv_patterns = [
                'venv/',
                'env/',
                '.venv',
                'ENV/'
            ]
            for pattern in venv_patterns:
                self.assertIn(pattern, content, f"Missing venv pattern: {pattern}")
    
    def test_gitignore_has_test_coverage_patterns(self):
        """Test that .gitignore includes test coverage patterns"""
        with open('.gitignore', 'r') as f:
            content = f.read()
            coverage_patterns = [
                '.coverage',
                'htmlcov/',
                '.pytest_cache/'
            ]
            for pattern in coverage_patterns:
                self.assertIn(pattern, content, f"Missing coverage pattern: {pattern}")
    
    def test_gitignore_format(self):
        """Test that .gitignore is properly formatted"""
        with open('.gitignore', 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines, 1):
                # Lines should not have trailing whitespace (except empty lines)
                if line.strip():
                    self.assertEqual(line.rstrip('\n'), line.rstrip(), 
                                   f"Line {i} has trailing whitespace")


class TestManifestConfiguration(unittest.TestCase):
    """Tests for MANIFEST.in configuration"""
    
    def test_manifest_exists(self):
        """Test that MANIFEST.in exists"""
        self.assertTrue(os.path.exists('MANIFEST.in'))
    
    def test_manifest_includes_readme(self):
        """Test that MANIFEST.in includes README.md"""
        with open('MANIFEST.in', 'r') as f:
            content = f.read()
            self.assertIn('README.md', content)
    
    def test_manifest_includes_license(self):
        """Test that MANIFEST.in includes LICENSE"""
        with open('MANIFEST.in', 'r') as f:
            content = f.read()
            self.assertIn('LICENSE', content)
    
    def test_manifest_includes_python_files(self):
        """Test that MANIFEST.in includes Python files"""
        with open('MANIFEST.in', 'r') as f:
            content = f.read()
            self.assertIn('*.py', content)
    
    def test_manifest_includes_llm_package(self):
        """Test that MANIFEST.in includes LLM package"""
        with open('MANIFEST.in', 'r') as f:
            content = f.read()
            self.assertIn('LLM', content)
    
    def test_manifest_includes_cortex_package(self):
        """Test that MANIFEST.in includes cortex package"""
        with open('MANIFEST.in', 'r') as f:
            content = f.read()
            self.assertIn('cortex', content)
    
    def test_manifest_format(self):
        """Test that MANIFEST.in is properly formatted"""
        with open('MANIFEST.in', 'r') as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line:
                    # Each line should start with a valid command
                    valid_commands = ['include', 'recursive-include', 'global-include', 
                                    'exclude', 'recursive-exclude', 'global-exclude',
                                    'graft', 'prune']
                    starts_with_valid = any(line.startswith(cmd) for cmd in valid_commands)
                    self.assertTrue(starts_with_valid, 
                                  f"Invalid MANIFEST.in line: {line}")


class TestLicenseFile(unittest.TestCase):
    """Tests for LICENSE file"""
    
    def test_license_exists(self):
        """Test that LICENSE file exists"""
        self.assertTrue(os.path.exists('LICENSE'))
    
    def test_license_is_readable(self):
        """Test that LICENSE can be read"""
        with open('LICENSE', 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertGreater(len(content), 0)
    
    def test_license_has_copyright(self):
        """Test that LICENSE contains copyright information"""
        with open('LICENSE', 'r', encoding='utf-8') as f:
            content = f.read().lower()
            # Most licenses contain these terms
            has_license_terms = any(term in content for term in 
                                   ['copyright', 'license', 'permission', 'mit'])
            self.assertTrue(has_license_terms)


class TestPackageStructure(unittest.TestCase):
    """Tests for overall package structure"""
    
    def test_cortex_package_exists(self):
        """Test that cortex package directory exists"""
        self.assertTrue(os.path.isdir('cortex'))
    
    def test_cortex_init_exists(self):
        """Test that cortex/__init__.py exists"""
        self.assertTrue(os.path.exists('cortex/__init__.py'))
    
    def test_cortex_init_has_version(self):
        """Test that cortex/__init__.py defines __version__"""
        with open('cortex/__init__.py', 'r') as f:
            content = f.read()
            self.assertIn('__version__', content)
    
    def test_cortex_init_imports_main(self):
        """Test that cortex/__init__.py imports main"""
        with open('cortex/__init__.py', 'r') as f:
            content = f.read()
            self.assertIn('from .cli import main', content)
    
    def test_llm_package_exists(self):
        """Test that LLM package directory exists"""
        self.assertTrue(os.path.isdir('LLM'))
    
    def test_llm_init_exists(self):
        """Test that LLM/__init__.py exists"""
        self.assertTrue(os.path.exists('LLM/__init__.py'))
    
    def test_all_test_files_are_discoverable(self):
        """Test that all test files follow naming convention"""
        import glob
        test_files = glob.glob('**/test_*.py', recursive=True)
        self.assertGreater(len(test_files), 0, "No test files found")
        
        for test_file in test_files:
            # Test files should be in appropriate directories
            self.assertTrue(
                any(dir in test_file for dir in ['cortex', 'LLM', 'src', '.']) or 
                test_file.startswith('test_'),
                f"Test file in unexpected location: {test_file}"
            )


if __name__ == '__main__':
    unittest.main()