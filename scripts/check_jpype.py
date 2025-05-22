#!/usr/bin/env python3
"""
JPype1 설치 상태를 확인하는 스크립트
"""

import os
import sys
import importlib
import subprocess

def check_pip_list():
    """pip list에서 JPype1 검색"""
    print("pip list에서 JPype1 검색 중...")
    try:
        result = subprocess.run(
            ["pip", "list"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        packages = result.stdout.splitlines()
        jpype_packages = [p for p in packages if "jpype" in p.lower()]
        
        if jpype_packages:
            print("설치된 JPype 패키지:")
            for pkg in jpype_packages:
                print(f"  {pkg}")
        else:
            print("설치된 JPype 패키지를 찾을 수 없습니다.")
    except subprocess.CalledProcessError as e:
        print(f"pip list 명령 실행 중 오류: {e}")

def check_import_jpype():
    """직접 jpype1 임포트 시도"""
    print("\njpype1 임포트 시도...")
    try:
        import jpype1
        print(f"성공: JPype1 버전 {jpype1.__version__}가 설치되어 있습니다.")
        print(f"JPype1 경로: {jpype1.__file__}")
        
        # JVM 시작 가능한지 테스트
        if not jpype1.isJVMStarted():
            try:
                jvm_path = jpype1.getDefaultJVMPath()
                print(f"JVM 경로: {jvm_path}")
                print("JVM 시작 시도...")
                jpype1.startJVM(jvm_path, "-Dfile.encoding=UTF-8", convertStrings=True)
                print("JVM 시작 성공!")
            except Exception as e:
                print(f"JVM 시작 실패: {e}")
        else:
            print("JVM이 이미 실행 중입니다.")
    except ImportError as e:
        print(f"jpype1 임포트 실패: {e}")
    except Exception as e:
        print(f"기타 오류: {e}")

def check_pythonpath():
    """Python 경로 확인"""
    print("\nPYTHONPATH 환경변수 확인:")
    python_path = os.environ.get("PYTHONPATH", "")
    if python_path:
        paths = python_path.split(os.pathsep)
        for p in paths:
            print(f"  {p}")
    else:
        print("  PYTHONPATH가 설정되지 않았습니다.")
    
    print("\n현재 Python의 sys.path:")
    for p in sys.path:
        print(f"  {p}")

def check_java_env():
    """Java 환경 확인"""
    print("\nJava 환경 확인:")
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        print(f"  JAVA_HOME: {java_home}")
        
        java_exe = os.path.join(java_home, "bin", "java")
        if os.path.exists(java_exe):
            print(f"  java 실행 파일 존재: {java_exe}")
        else:
            print(f"  경고: java 실행 파일이 없습니다: {java_exe}")
    else:
        print("  JAVA_HOME이 설정되지 않았습니다.")
    
    # java 명령어 찾기
    try:
        result = subprocess.run(
            ["which", "java"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        java_path = result.stdout.strip()
        print(f"  시스템 java 경로: {java_path}")
        
        # java 버전 확인
        result = subprocess.run(
            ["java", "-version"], 
            capture_output=True, 
            text=True, 
            check=False
        )
        version_info = result.stderr.strip() if result.stderr else result.stdout.strip()
        print(f"  Java 버전 정보: {version_info}")
    except subprocess.CalledProcessError:
        print("  시스템에서 java를 찾을 수 없습니다.")
    except Exception as e:
        print(f"  Java 확인 중 오류: {e}")

def suggest_solutions():
    """문제 해결 방법 제안"""
    print("\n=== 문제 해결 방법 ===")
    print("1. JPype1 재설치:")
    print("   pip uninstall jpype1")
    print("   pip install jpype1==1.4.1")
    print("\n2. Java JDK 설치 확인:")
    print("   sudo apt install default-jdk   # Ubuntu")
    print("   brew install openjdk           # macOS")
    print("\n3. JAVA_HOME 환경변수 설정:")
    print("   export JAVA_HOME=/usr/lib/jvm/default-java  # Ubuntu 예시")
    print("\n4. 특정 버전 시도:")
    print("   pip install jpype1==0.7.5")
    print("   또는")
    print("   pip install JPype1-py3==0.5.5.4")
    print("\n5. hanolcare_crawler 모듈 코드 수정:")
    print("   import jpype1 대신 try/except 블록 사용")

if __name__ == "__main__":
    print("=== JPype1 설치 상태 진단 ===")
    print(f"Python 버전: {sys.version}")
    print(f"실행 경로: {sys.executable}")
    
    check_pip_list()
    check_import_jpype()
    check_pythonpath()
    check_java_env()
    suggest_solutions()
