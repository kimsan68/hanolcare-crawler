#!/bin/bash

# KoNLPy를 위한 Java 설정 도움말 스크립트

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}       KoNLPy를 위한 Java 설정 도움말       ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo
}

check_java() {
    echo -e "${BLUE}[1] Java 설치 확인${NC}"
    
    if command -v java &> /dev/null; then
        java_version=$(java -version 2>&1 | head -n 1)
        echo -e "${GREEN}✓ Java가 설치되어 있습니다: $java_version${NC}"
    else
        echo -e "${RED}✗ Java가 설치되어 있지 않습니다.${NC}"
        echo -e "${YELLOW}다음 명령으로 Java를 설치하세요:${NC}"
        
        if [ -f /etc/debian_version ]; then
            # Debian/Ubuntu 계열
            echo -e "  ${GREEN}sudo apt update${NC}"
            echo -e "  ${GREEN}sudo apt install -y default-jdk${NC}"
        elif [ -f /etc/redhat-release ]; then
            # Red Hat/CentOS/Fedora 계열
            echo -e "  ${GREEN}sudo yum install -y java-11-openjdk-devel${NC}"
        elif [ -f /etc/arch-release ]; then
            # Arch Linux
            echo -e "  ${GREEN}sudo pacman -S jdk-openjdk${NC}"
        elif [ "$(uname)" == "Darwin" ]; then
            # macOS
            echo -e "  ${GREEN}brew install --cask adoptopenjdk${NC}"
            echo -e "  또는 https://adoptopenjdk.net/ 에서 JDK를 다운로드하세요."
        else
            echo -e "  https://adoptopenjdk.net/ 에서 JDK를 다운로드하세요."
        fi
        return 1
    fi
    return 0
}

check_java_home() {
    echo -e "\n${BLUE}[2] JAVA_HOME 환경변수 확인${NC}"
    
    if [ -n "$JAVA_HOME" ]; then
        if [ -d "$JAVA_HOME" ] && [ -x "$JAVA_HOME/bin/java" ]; then
            echo -e "${GREEN}✓ JAVA_HOME이 올바르게 설정되어 있습니다: $JAVA_HOME${NC}"
        else
            echo -e "${RED}✗ JAVA_HOME이 설정되어 있지만 경로가 올바르지 않습니다: $JAVA_HOME${NC}"
            find_and_set_java_home
        fi
    else
        echo -e "${YELLOW}! JAVA_HOME이 설정되어 있지 않습니다.${NC}"
        find_and_set_java_home
    fi
}

find_and_set_java_home() {
    echo -e "${YELLOW}자동으로 Java 경로를 찾는 중...${NC}"
    
    # 가능한 Java 설치 경로들
    paths_to_check=(
        "/usr/lib/jvm/default-java"
        "/usr/lib/jvm/java-11-openjdk-amd64"
        "/usr/lib/jvm/java-8-openjdk-amd64" 
        "/usr/lib/jvm/java"
    )
    
    # 현재 OS가 macOS인 경우
    if [ "$(uname)" == "Darwin" ]; then
        paths_to_check+=(
            "/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home"
            "/Library/Java/JavaVirtualMachines/adoptopenjdk-11.jdk/Contents/Home"
            "/Library/Java/JavaVirtualMachines/jdk1.8.0_301.jdk/Contents/Home"
            "/usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home"
        )
    fi
    
    # 시스템에서 추가 JVM 위치 찾기
    if [ -d "/usr/lib/jvm" ]; then
        for dir in /usr/lib/jvm/*; do
            if [ -d "$dir" ] && [ -x "$dir/bin/java" ]; then
                paths_to_check+=("$dir")
            fi
        done
    fi
    
    # 유효한 Java 설치 찾기
    valid_java_path=""
    for path in "${paths_to_check[@]}"; do
        if [ -d "$path" ] && [ -x "$path/bin/java" ]; then
            valid_java_path="$path"
            break
        fi
    done
    
    if [ -n "$valid_java_path" ]; then
        echo -e "${GREEN}✓ 유효한 Java 경로를 찾았습니다: $valid_java_path${NC}"
        echo -e "${YELLOW}다음과 같이 JAVA_HOME을 설정하세요:${NC}"
        echo -e "  ${GREEN}export JAVA_HOME=\"$valid_java_path\"${NC}"
        
        # 현재 세션에 적용
        echo -e "\n현재 세션에 JAVA_HOME을 설정하시겠습니까? (y/n)"
        read -r set_now
        if [[ $set_now =~ ^[Yy]$ ]]; then
            export JAVA_HOME="$valid_java_path"
            echo -e "${GREEN}✓ 현재 세션에 JAVA_HOME이 설정되었습니다.${NC}"
        fi
        
        # 영구 설정 안내
        echo -e "\n${YELLOW}JAVA_HOME을 영구적으로 설정하려면 다음 줄을 ~/.bashrc (또는 ~/.zshrc)에 추가하세요:${NC}"
        echo -e "  ${GREEN}export JAVA_HOME=\"$valid_java_path\"${NC}"
    else
        echo -e "${RED}✗ 유효한 Java 설치를 찾을 수 없습니다.${NC}"
        echo -e "${YELLOW}Java JDK를 설치한 후 다시 시도하세요.${NC}"
    fi
}

check_jpype() {
    echo -e "\n${BLUE}[3] JPype1 설치 확인${NC}"
    
    if python3 -c "import jpype1" 2>/dev/null; then
        echo -e "${GREEN}✓ JPype1이 설치되어 있습니다.${NC}"
    else
        echo -e "${RED}✗ JPype1이 설치되어 있지 않습니다.${NC}"
        echo -e "${YELLOW}다음 명령으로 JPype1을 설치하세요:${NC}"
        echo -e "  ${GREEN}pip install JPype1${NC}"
        
        # 설치 제안
        echo -e "\nJPype1을 지금 설치하시겠습니까? (y/n)"
        read -r install_now
        if [[ $install_now =~ ^[Yy]$ ]]; then
            pip install JPype1
            echo -e "${GREEN}✓ JPype1 설치 시도 완료.${NC}"
        fi
    fi
}

check_konlpy() {
    echo -e "\n${BLUE}[4] KoNLPy 설치 확인${NC}"
    
    if python3 -c "import konlpy" 2>/dev/null; then
        echo -e "${GREEN}✓ KoNLPy가 설치되어 있습니다.${NC}"
        
        # KoNLPy Okt 테스트
        echo -e "\n${YELLOW}KoNLPy Okt 분석기를 테스트하시겠습니까? (y/n)${NC}"
        read -r test_konlpy
        if [[ $test_konlpy =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}KoNLPy Okt 테스트 중...${NC}"
            python3 -c "from konlpy.tag import Okt; okt = Okt(); print('테스트 성공:', okt.nouns('안녕하세요 KoNLPy 테스트입니다.'))" || echo -e "${RED}테스트 실패${NC}"
        fi
    else
        echo -e "${RED}✗ KoNLPy가 설치되어 있지 않습니다.${NC}"
        echo -e "${YELLOW}다음 명령으로 KoNLPy를 설치하세요:${NC}"
        echo -e "  ${GREEN}pip install konlpy${NC}"
        
        # 설치 제안
        echo -e "\nKoNLPy를 지금 설치하시겠습니까? (y/n)"
        read -r install_now
        if [[ $install_now =~ ^[Yy]$ ]]; then
            pip install konlpy
            echo -e "${GREEN}✓ KoNLPy 설치 시도 완료.${NC}"
        fi
    fi
}

print_summary() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}                   요약                      ${NC}"
    echo -e "${BLUE}============================================${NC}"
    
    echo -e "KoNLPy가 제대로 작동하려면 다음이 필요합니다:"
    echo -e "1. Java JDK 8 이상 설치"
    echo -e "2. JAVA_HOME 환경변수가 올바르게 설정"
    echo -e "3. JPype1 패키지 설치"
    echo -e "4. KoNLPy 패키지 설치"
    
    echo -e "\n${YELLOW}모든 설정이 완료되면 다음 명령으로 크롤러를 실행하세요:${NC}"
    echo -e "  ${GREEN}./run.sh${NC}"
    echo -e "  또는"
    echo -e "  ${GREEN}python3 -m hanolcare_crawler --cli${NC}"
}

# 메인 함수
main() {
    print_header
    check_java
    check_java_home
    check_jpype
    check_konlpy
    print_summary
}

# 스크립트 실행
main
