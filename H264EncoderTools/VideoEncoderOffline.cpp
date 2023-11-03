#include <vector>
#include <string>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif
#include "cJSON.h"
#include "VideoEncoderX264.h"

typedef struct FrameInfo {
  FrameType frameType;
  int64_t timeStamp;
  int frameSize;
} FrameInfo;

typedef struct OffLineEncodeParam {
  //std::string uniqueId;
  int width = 0;
  int height = 0;
  double frameRate = 24.0;
  int hasAlpha = 0;
  int maxKeyFrameInterval = 60;
  int quality = 80;
} OffLineEncodeParam;

static cJSON* ParseJsonFile(std::string path) {
  char text[4*1024];
  auto fp = fopen(path.c_str(), "rt");
  if (fp == nullptr) {
    return nullptr;
  }
  
  fseek(fp, 0, SEEK_END);
  auto len = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  if (len == 0 || len >= sizeof(text)) {
    printf("ParseJsonFile size error!\n");
    fclose(fp);
    return nullptr;
  }
  len = fread(text, 1, len, fp);
  fclose(fp);
  text[len] = '\0';
  
  auto root = cJSON_Parse(text);
  return root;
}

template <typename T>
static bool GetIntValue(cJSON* root, std::string str, T& value) {
  auto item = cJSON_GetObjectItem(root, str.c_str());
  if (item != nullptr && item->type == cJSON_Int) {
    value = static_cast<T>(item->valueint);
    return true;
  } else {
    return false;
  }
}

static bool GetDoubleValue(cJSON* root, std::string str, double& value) {
  auto item = cJSON_GetObjectItem(root, str.c_str());
  if (item != nullptr && item->type == cJSON_Double) {
    value = static_cast<double>(item->valuedouble);
    return true;
  } else {
    return false;
  }
}

static bool WriteDataToFile(uint8_t* data, int size, std::string path) {
  auto fp = fopen(path.c_str(), "wb");
  if (fp == nullptr) {
    return false;
  }
  fwrite(data, 1, size, fp);
  fflush(fp);
  fclose(fp);
  return true;
}

static bool WriteFrameInfo(FrameInfo& frameInfo, std::string path) {
  auto fp = fopen(path.c_str(), "wt");
  if (fp == nullptr) {
    return false;
  }
  fprintf(fp, "{ \"FrameType\": %d, \"TimeStamp\": %.0f, \"FrameSize\": %d }",
          frameInfo.frameType, (float)frameInfo.timeStamp, frameInfo.frameSize);
  fclose(fp);
  return true;
}

static bool ReadFrameInfo(FrameInfo& frameInfo, std::string path) {
  auto root = ParseJsonFile(path);
  if (root == nullptr) {
    return false;
  }
  
  bool ret = true;
  int frameType = -1;
  ret = ret && GetIntValue(root, "FrameType", frameType);
  ret = ret && GetIntValue(root, "TimeStamp", frameInfo.timeStamp);
  ret = ret && GetIntValue(root, "FrameSize", frameInfo.frameSize);
  frameInfo.frameType = static_cast<FrameType>(frameType);
  
  cJSON_Delete(root);
  return ret;
}

static bool ReadParamFromFile(OffLineEncodeParam* param, std::string path) {
  auto root = ParseJsonFile(path);
  if (root == nullptr) {
    return false;
  }
  
  bool ret = true;
  ret = ret && GetIntValue(root, "Width", param->width);
  ret = ret && GetIntValue(root, "Height", param->height);
  ret = ret && GetDoubleValue(root, "FrameRate", param->frameRate);
  ret = ret && GetIntValue(root, "HasAlpha", param->hasAlpha);
  ret = ret && GetIntValue(root, "MaxKeyFrameInterval", param->maxKeyFrameInterval);
  ret = ret && GetIntValue(root, "Quality", param->quality);
  
  cJSON_Delete(root);
  return ret;
}

static bool ReadEndParam(bool& hasEnd, bool& bEarlyExit, std::string path) {
  auto root = ParseJsonFile(path);
  if (root == nullptr) {
    return false;
  }
  
  int end = 0;
  int exit = 0;
  
  bool ret = true;
  ret = ret && GetIntValue(root, "HasEnd", end);
  ret = ret && GetIntValue(root, "EarlyExit", exit);
  
  hasEnd = !!end;
  bEarlyExit = !!exit;
  
  cJSON_Delete(root);
  return ret;
}

static bool WriteEndParam(bool hasEnd, bool bEarlyExit, std::string path) {
  auto fp = fopen(path.c_str(), "wt");
  if (fp == nullptr) {
    return false;
  }
  fprintf(fp, "{ \"HasEnd\": %d, \"EarlyExit\": %d }",
          hasEnd ? 1 : 0,
          bEarlyExit ? 1 : 0);
  fclose(fp);
  return true;
}

static bool ReadYUVPlane(uint8_t* data, int stride, int width, int height, FILE* fp) {
  for (int j = 0; j < height; j++) {
    auto size = fread(data + j*stride, 1, width, fp);
    if (size != width) {
      return false;
    }
  }
  return true;
}

static bool ReadYUVData(uint8_t* data[4], int stride[4], int width, int height, std::string path) {
  auto fp = fopen(path.c_str(), "rb");
  if (fp == nullptr) {
    return false;
  }
  bool ret = true;
  ret = ret && ReadYUVPlane(data[0], stride[0], width/1, height/1, fp);
  ret = ret && ReadYUVPlane(data[1], stride[1], width/2, height/2, fp);
  ret = ret && ReadYUVPlane(data[2], stride[2], width/2, height/2, fp);
  fclose(fp);
  return ret;
}

static bool WriteYUVPlane(uint8_t* data, int stride, int width, int height, FILE* fp) {
  for (int j = 0; j < height; j++) {
    auto size = fwrite(data + j*stride, 1, width, fp);
    if (static_cast<int>(size) != width) {
      printf("write error\n");
      return false;
    }
  }
  fflush(fp);
  return true;
}

static bool WriteYUVData(uint8_t* data[4], int stride[4], int width, int height, std::string path) {
  auto fp = fopen(path.c_str(), "wb");
  if (fp == nullptr) {
    return false;
  }
  bool ret = true;
  ret = ret && WriteYUVPlane(data[0], stride[0], width/1, height/1, fp);
  ret = ret && WriteYUVPlane(data[1], stride[1], width/2, height/2, fp);
  ret = ret && WriteYUVPlane(data[2], stride[2], width/2, height/2, fp);
  fflush(fp);
  fclose(fp);
  return ret;
}

bool YuvToH264(std::string rootPath) {
  printf("EncodeFile\n");
  OffLineEncodeParam param;
  auto ret = ReadParamFromFile(&param, rootPath + "EncoderParam.txt");
  if (!ret) {
    printf("ReadParamFromFile fail\n");
    return false;
  }
  
  int width = param.width;
  int height = param.height;
  double frameRate = param.frameRate;
  bool hasAlpha = param.hasAlpha;
  int maxKeyFrameInterval = param.maxKeyFrameInterval;
  int quality = param.quality;
  
  auto encoderX264 = new VideoEncoderX264();
  encoderX264->open(width, height, frameRate, hasAlpha, maxKeyFrameInterval, quality);
  
  // write header
  uint8_t* nal[16];
  int size[16];
  int count = encoderX264->encodeHeaders(nal, size);
  if (count >= 2) {
    WriteDataToFile(nal[1], size[1], rootPath + "Header-1.dat");
    WriteDataToFile(nal[0], size[0], rootPath + "Header-0.dat");
  }
  
  bool hasEnd = false;
  bool bEarlyExit = false;
  int inFrame = 0;
  int outFrame = 0;
  do {
    bool ret = ReadEndParam(hasEnd, bEarlyExit, rootPath + "InEnd.txt");
    if (ret && bEarlyExit) {
      printf("bEarlyExit==true\n");
      break;
    }
    
    FrameInfo inFrameInfo;
    bool hasYUV = false;
    auto frameType = FrameType::FRAME_TYPE_AUTO;
    
    uint8_t* data[4] = { nullptr };
    int stride[4] = { 0 };
    encoderX264->getInputFrameBuf(data, stride);
    
    ret = ReadFrameInfo(inFrameInfo, rootPath + "InFrameInfo-" + std::to_string(inFrame) + ".txt");
    if (ret) {
      auto yuvPath = rootPath + "YUV-" + std::to_string(inFrame) + ".yuv";
      ret = ReadYUVData(data, stride, width, height, yuvPath);
      if (ret) {
        frameType = inFrameInfo.frameType;
        hasYUV = true;
        inFrame++;
        
        std::string cmd = "rm -rf \'" + yuvPath + "\'\n";
        system(cmd.c_str());
      }
      
      //if (ret) {
      //  ret = WriteYUVData(data, stride, width, height, rootPath + "YUV-" + std::to_string(inFrame) + "-back.yuv");
      //}
    }
    
    if (hasYUV || hasEnd != 0) {
      uint8_t* stream = nullptr;
      int64_t outTimeStamp = 0;
      int size = encoderX264->encodeFrame(data, stride, &stream, &frameType, &outTimeStamp);
      if (stream != nullptr && size > 0) {
        WriteDataToFile(stream, size, rootPath + "H264-" + std::to_string(outFrame) + ".264");
        FrameInfo outFrameInfo;
        outFrameInfo.frameType = frameType;
        outFrameInfo.timeStamp = outTimeStamp;
        outFrameInfo.frameSize = size;
        printf("33 outFrame=%d size = %d\n", outFrame, size);
        WriteFrameInfo(outFrameInfo, rootPath + "OutFrameInfo-" + std::to_string(outFrame) + ".txt");
        outFrame++;
      }
    } else {
#ifdef _WIN32
      Sleep(1);
#else
      usleep(1000);
#endif
    }
    if (hasEnd && outFrame == inFrame) {
      break;
    }
  } while (true);
  
  delete encoderX264;
  WriteEndParam(outFrame==inFrame, bEarlyExit, rootPath + "OutEnd.txt");
  return true;
}
