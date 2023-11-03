#ifndef PAGEXPORTER_VIDEO_ENCODER_H
#define PAGEXPORTER_VIDEO_ENCODER_H

//#include "exports/DataTypes.h"
#include <string>

#define SIZE_ALIGN(x) (((x) + 1) & ~0x01)

typedef enum {
  FRAME_TYPE_AUTO = -1,
  FRAME_TYPE_P = 0,
  FRAME_TYPE_I = 1,
} FrameType;

class VideoEncoder {
public:
  //static std::unique_ptr<VideoEncoder> MakeVideoEncoder(bool bHW = false);
  virtual ~VideoEncoder() = default;
  virtual bool open(int width, int height, double frameRate, bool hasAlpha,
                    int maxKeyFrameInterval = 0, int quality = 0) = 0;
  virtual int encodeFrame(uint8_t* data[], int stride[], uint8_t** pOutStream,
                          FrameType* pFrameType, int64_t* pOutTimeStamp) = 0;
  virtual int encodeHeaders(uint8_t* header[], int headerSize[]) = 0;
  virtual void getInputFrameBuf(uint8_t* data[], int stride[]) = 0;
  
protected:
  int width = 0;
  int height = 0;
  double frameRate = 24.0;
};

#endif  // PAGEXPORTER_VIDEO_ENCODER_H
