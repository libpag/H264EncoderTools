#ifndef PAGEXPORTER_VIDEO_ENCODER_X264_H
#define PAGEXPORTER_VIDEO_ENCODER_X264_H

#include "VideoEncoder.h"
#include "x264.h"

class VideoEncoderX264 : public VideoEncoder {
public:
  VideoEncoderX264() {};
  ~VideoEncoderX264() override;
  bool open(int width, int height, double frameRate, bool hasAlpha, int maxKeyFrameInterval = 0, int quality = 0) override;
  int encodeFrame(uint8_t* data[], int stride[], uint8_t** pOutStream,
                  FrameType* pFrameType, int64_t* pOutTimeStamp) override;
  int encodeHeaders(uint8_t* header[], int headerSize[]) override;
  void getInputFrameBuf(uint8_t* data[], int stride[]) override;
  
private:
  x264_param_t param;
  x264_picture_t pic;
  x264_picture_t pic_out;
  x264_t* h;
  int i_frame = 0;
  x264_nal_t* nal;
  int i_nal;
};

#endif  // PAGEXPORTER_VIDEO_ENCODER_X264_H
