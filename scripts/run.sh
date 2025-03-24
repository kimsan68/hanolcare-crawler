#!/bin/bash

# 정부24 민원 수집 프로그램 실행 스크립트

# 디렉토리 경로 설정
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 필요한 패키지 확인
check_packages() {
    echo "의존성 패키지 확인 중..."
    
    # requirements.txt 존재 확인
    if [ -f "requirements.txt" ]; then
        missing_packages=()
        
        while IFS= read -r line || [ -n "$line" ]; do
            # 주석이나 빈 줄 무시
            if [[ $line =~ ^#.*$ ]] || [[ -z $line ]]; then
                continue
            fi
            
            # 패키지 이름 추출
            pkg_name=$(echo "$line" | sed -E 's/([a-zA-Z0-9_\-]+).*/\1/')
            
            # 패키지 설치 여부 확인
            if ! python3 -c "import $pkg_name" 2>/dev/null; then
                missing_packages+=("$pkg_name")
            fi
        done < "requirements.txt"
        
        if [ ${#missing_packages[@]} -gt 0 ]; then
            echo "다음 패키지가 설치되지 않았습니다:"
            for pkg in "${missing_packages[@]}"; do
                echo " - $pkg"
            done
            
            read -p "필요한 패키지를 설치하시겠습니까? (y/n): " install_choice
            if [[ $install_choice =~ ^[Yy]$ ]]; then
                pip install -r requirements.txt
                echo "패키지 설치 완료"
            else
                echo "경고: 일부 패키지가 설치되지 않아 프로그램이 제대로 작동하지 않을 수 있습니다."
            fi
        else
            echo "모든 필요 패키지가 설치되어 있습니다."
        fi
    else
        echo "requirements.txt 파일을 찾을 수 없습니다."
    fi
}

# Playwright 설치 확인
check_playwright() {
    if ! python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
        echo "Playwright가 설치되지 않았습니다."
        return 1
    fi
    
    if ! python3 -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__()" 2>/dev/null; then
        echo "Playwright 브라우저가 설치되지 않았습니다."
        read -p "Playwright 브라우저를 설치하시겠습니까? (y/n): " install_choice
        if [[ $install_choice =~ ^[Yy]$ ]]; then
            python3 -m playwright install
            echo "Playwright 브라우저 설치 완료"
        else
            echo "경고: Playwright 브라우저가 설치되지 않아 일부 기능이 제한될 수 있습니다."
        fi
    else
        echo "Playwright가 정상적으로 설치되어 있습니다."
    fi
}

# Java 설치 확인 및 JAVA_HOME 설정
check_java() {
    echo "Java 환경 확인 중..."
    
    # java 명령어 확인
    if ! command -v java &> /dev/null; then
        echo "Java가 설치되어 있지 않습니다."
        read -p "Java를 설치하시겠습니까? 한국어 분석(KoNLPy)에 필요합니다. (y/n): " install_choice
        if [[ $install_choice =~ ^[Yy]$ ]]; then
            if [ -f /etc/debian_version ]; then
                # Debian/Ubuntu 계열
                sudo apt update
                sudo apt install -y default-jdk
            elif [ -f /etc/redhat-release ]; then
                # Red Hat/CentOS/Fedora 계열
                sudo yum install -y java-11-openjdk-devel
            elif [ -f /etc/arch-release ]; then
                # Arch Linux
                sudo pacman -S jdk-openjdk
            elif command -v brew &> /dev/null; then
                # macOS + Homebrew
                brew install openjdk
            else
                echo "알 수 없는 운영체제입니다. Java를 수동으로 설치해주세요."
                echo "https://adoptopenjdk.net/ 에서 JDK를 다운로드할 수 있습니다."
                return 1
            fi
        else
            echo "경고: Java 없이 계속하면 한국어 분석 기능(KoNLPy)이 작동하지 않습니다."
            return 0
        fi
    fi
    
    # Java 버전 확인
    java_version=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}')
    echo "Java 버전: $java_version"
    
    # JAVA_HOME 환경변수 설정
    if [ -z "$JAVA_HOME" ]; then
        # Java 경로 찾기
        if command -v javac &> /dev/null; then
            java_path=$(dirname $(dirname $(readlink -f $(which javac))))
            echo "Java 경로가 발견되었습니다: $java_path"
            export JAVA_HOME="$java_path"
            echo "JAVA_HOME을 $java_path 로 설정합니다."
            
            # 현재 세션에만 적용
            echo "현재 세션에만 JAVA_HOME이 설정됩니다."
            echo "영구적으로 설정하려면 ~/.bashrc 파일에 다음 줄을 추가하세요:"
            echo "export JAVA_HOME=$java_path"
        else
            echo "Java 컴파일러(javac)를 찾을 수 없습니다. JDK가 아닌 JRE만 설치되었을 수 있습니다."
            echo "KoNLPy에는 전체 JDK가 필요합니다. 설치하려면:"
            echo "Ubuntu: sudo apt install default-jdk"
            echo "CentOS: sudo yum install java-11-openjdk-devel"
        fi
    else
        echo "JAVA_HOME이 이미 설정되어 있습니다: $JAVA_HOME"
    fi
}

# 메인 실행 함수
main() {
    echo "===== 정부24 민원 수집 프로그램 ====="
    
    # 기본 환경 확인
    check_packages
    check_playwright
    check_java
    
    echo "크롤러를 시작합니다..."
    python3 crawler.py --cli
}

# 스크립트 실행
main "$@"
