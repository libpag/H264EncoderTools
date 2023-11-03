//
//  main.cpp
//  OfflineX264
//
//  Created by 陈新星 on 2023/9/25.
//

#include <iostream>
#include "VideoEncoderOffline.h"

int main(int argc, const char * argv[]) {
  
  //YuvToH264("/Users/chenxinxing/Library/Application Support/PAGExporter/OffLineFolder/"); return 0;
  
  if (argc < 2) {
    printf("param error!\n");
    return -1;
  }
  
  YuvToH264(argv[1]);
  
  return 0;
}
