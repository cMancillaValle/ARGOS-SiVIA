/**
 * frontend/js/transmilenio-layout.js
 * Layout esquemático oficial de TransMilenio SiViA basado en mapaTM.
 * 100% libre de coordenadas GPS y dependencias externas.
 */

const TRANSMILENIO_LAYOUT = {
  "viewBox": {
    "width": 1750,
    "height": 1050
  },
  "stations": {
    "TM-B-01": {
      "x": 110,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "B"
    },
    "TM-B-02": {
      "x": 140,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-03": {
      "x": 170,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-04": {
      "x": 200,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-05": {
      "x": 230,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-06": {
      "x": 260,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-07": {
      "x": 290,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-08": {
      "x": 320,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-09": {
      "x": 350,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-10": {
      "x": 380,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-11": {
      "x": 410,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-12": {
      "x": 440,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "B"
    },
    "TM-B-13": {
      "x": 470,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-14": {
      "x": 500,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "B"
    },
    "TM-B-15": {
      "x": 530,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "B"
    },
    "TM-A-01": {
      "x": 570,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-02": {
      "x": 608,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-03": {
      "x": 646,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-04": {
      "x": 684,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-05": {
      "x": 722,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-06": {
      "x": 760,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-07": {
      "x": 798,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-08": {
      "x": 836,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-09": {
      "x": 874,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-10": {
      "x": 912,
      "y": 190,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "A"
    },
    "TM-A-11": {
      "x": 950,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-A-12": {
      "x": 988,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "A"
    },
    "TM-A-13": {
      "x": 1026,
      "y": 190,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "A"
    },
    "TM-C-01": {
      "x": 160,
      "y": 620,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "C"
    },
    "TM-C-02": {
      "x": 160,
      "y": 580,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-03": {
      "x": 160,
      "y": 545,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-04": {
      "x": 160,
      "y": 510,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-05": {
      "x": 160,
      "y": 475,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-06": {
      "x": 185,
      "y": 440,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "C"
    },
    "TM-C-07": {
      "x": 215,
      "y": 410,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-08": {
      "x": 245,
      "y": 380,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-09": {
      "x": 280,
      "y": 355,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-10": {
      "x": 325,
      "y": 355,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-11": {
      "x": 370,
      "y": 355,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-C-12": {
      "x": 415,
      "y": 355,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "C"
    },
    "TM-D-01": {
      "x": 280,
      "y": 750,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "D"
    },
    "TM-D-02": {
      "x": 280,
      "y": 715,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-03": {
      "x": 280,
      "y": 680,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-04": {
      "x": 280,
      "y": 645,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "D"
    },
    "TM-D-05": {
      "x": 280,
      "y": 610,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-06": {
      "x": 280,
      "y": 575,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-07": {
      "x": 310,
      "y": 540,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-08": {
      "x": 345,
      "y": 505,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-D-09": {
      "x": 380,
      "y": 470,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "D"
    },
    "TM-D-10": {
      "x": 435,
      "y": 400,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "D"
    },
    "TM-D-11": {
      "x": 500,
      "y": 310,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "D"
    },
    "TM-G-10": {
      "x": 550,
      "y": 440,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-07": {
      "x": 600,
      "y": 440,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-04": {
      "x": 655,
      "y": 440,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-05": {
      "x": 715,
      "y": 440,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-06": {
      "x": 780,
      "y": 440,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-G-09": {
      "x": 860,
      "y": 440,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-G-08": {
      "x": 930,
      "y": 440,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-08": {
      "x": 1080,
      "y": 340,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-09": {
      "x": 1195,
      "y": 490,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-E-10": {
      "x": 1235,
      "y": 520,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "E"
    },
    "TM-K-01": {
      "x": 730,
      "y": 890,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "K"
    },
    "TM-K-02": {
      "x": 730,
      "y": 845,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-03": {
      "x": 730,
      "y": 800,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-04": {
      "x": 730,
      "y": 755,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-05": {
      "x": 730,
      "y": 710,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-06": {
      "x": 730,
      "y": 665,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-07": {
      "x": 730,
      "y": 620,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-08": {
      "x": 730,
      "y": 575,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-09": {
      "x": 760,
      "y": 535,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-10": {
      "x": 800,
      "y": 495,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-K-11": {
      "x": 870,
      "y": 375,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "estacion",
      "troncalId": "K"
    },
    "TM-F-01": {
      "x": 1170,
      "y": 810,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "F"
    },
    "TM-F-12": {
      "x": 1125,
      "y": 810,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-13": {
      "x": 1060,
      "y": 810,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-14": {
      "x": 1075,
      "y": 755,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-15": {
      "x": 1075,
      "y": 715,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-02": {
      "x": 1060,
      "y": 670,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "F"
    },
    "TM-F-03": {
      "x": 1045,
      "y": 630,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-04": {
      "x": 1030,
      "y": 590,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-05": {
      "x": 1005,
      "y": 555,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-06": {
      "x": 985,
      "y": 520,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-07": {
      "x": 965,
      "y": 485,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-08": {
      "x": 965,
      "y": 450,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-09": {
      "x": 965,
      "y": 415,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-10": {
      "x": 965,
      "y": 380,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "F"
    },
    "TM-F-11": {
      "x": 985,
      "y": 340,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "F"
    },
    "TM-G-07": {
      "x": 1080,
      "y": 440,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": true,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-06": {
      "x": 1120,
      "y": 440,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-05": {
      "x": 1160,
      "y": 465,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-02": {
      "x": 1210,
      "y": 555,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "G"
    },
    "TM-G-04": {
      "x": 1210,
      "y": 595,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-03": {
      "x": 1210,
      "y": 635,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-15": {
      "x": 1210,
      "y": 670,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-13": {
      "x": 1210,
      "y": 705,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-14": {
      "x": 1210,
      "y": 740,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-01": {
      "x": 1210,
      "y": 785,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "G"
    },
    "TM-G-11": {
      "x": 1320,
      "y": 880,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "G"
    },
    "TM-G-12": {
      "x": 1380,
      "y": 930,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "G"
    },
    "TM-H-06": {
      "x": 1050,
      "y": 260,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-05": {
      "x": 1150,
      "y": 260,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-07": {
      "x": 1200,
      "y": 290,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-08": {
      "x": 1240,
      "y": 325,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-04": {
      "x": 1280,
      "y": 365,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-09": {
      "x": 1320,
      "y": 410,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-10": {
      "x": 1360,
      "y": 455,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-11": {
      "x": 1395,
      "y": 490,
      "labelPosition": "left",
      "labelOffsetX": -10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-03": {
      "x": 1430,
      "y": 490,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "H"
    },
    "TM-H-12": {
      "x": 1465,
      "y": 490,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-15": {
      "x": 1495,
      "y": 490,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-16": {
      "x": 1525,
      "y": 490,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-01": {
      "x": 1565,
      "y": 490,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "H"
    },
    "TM-H-13": {
      "x": 1360,
      "y": 520,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-14": {
      "x": 1360,
      "y": 560,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "H"
    },
    "TM-H-02": {
      "x": 1360,
      "y": 605,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "H"
    },
    "TM-J-01": {
      "x": 985,
      "y": 120,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "J"
    },
    "TM-J-02": {
      "x": 985,
      "y": 60,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "estacion",
      "troncalId": "J"
    },
    "TM-L-02": {
      "x": 870,
      "y": 140,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": true,
      "tipo": "intermedio",
      "troncalId": "L"
    },
    "TM-L-04": {
      "x": 930,
      "y": 140,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-03": {
      "x": 985,
      "y": 140,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-05": {
      "x": 1060,
      "y": 140,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-06": {
      "x": 1120,
      "y": 140,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-07": {
      "x": 1180,
      "y": 140,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-08": {
      "x": 1250,
      "y": 140,
      "labelPosition": "bottom",
      "labelOffsetX": 0,
      "labelOffsetY": 14,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-09": {
      "x": 1330,
      "y": 140,
      "labelPosition": "top",
      "labelOffsetX": 0,
      "labelOffsetY": -10,
      "interchange": false,
      "tipo": "estacion",
      "troncalId": "L"
    },
    "TM-L-01": {
      "x": 1450,
      "y": 140,
      "labelPosition": "right",
      "labelOffsetX": 10,
      "labelOffsetY": 4,
      "interchange": true,
      "tipo": "portal",
      "troncalId": "L"
    }
  },
  "corridors": [
    {
      "id": "B",
      "troncalId": "B",
      "label": "Troncal Norte (B)",
      "color": "#009639",
      "path": "M 110 190 L 530 190",
      "stationIds": [
        "TM-B-01",
        "TM-B-02",
        "TM-B-03",
        "TM-B-04",
        "TM-B-05",
        "TM-B-06",
        "TM-B-07",
        "TM-B-08",
        "TM-B-09",
        "TM-B-10",
        "TM-B-11",
        "TM-B-12",
        "TM-B-13",
        "TM-B-14",
        "TM-B-15"
      ]
    },
    {
      "id": "A",
      "troncalId": "A",
      "label": "Troncal Caracas (A)",
      "color": "#E8001D",
      "path": "M 530 190 L 1030 190",
      "stationIds": [
        "TM-A-01",
        "TM-A-02",
        "TM-A-03",
        "TM-A-04",
        "TM-A-05",
        "TM-A-06",
        "TM-A-07",
        "TM-A-08",
        "TM-A-09",
        "TM-A-10",
        "TM-A-11",
        "TM-A-12",
        "TM-A-13"
      ]
    },
    {
      "id": "C",
      "troncalId": "C",
      "label": "Troncal Suba (C)",
      "color": "#F4A900",
      "path": "M 160 620 L 160 480 L 280 355 L 430 355",
      "stationIds": [
        "TM-C-01",
        "TM-C-02",
        "TM-C-03",
        "TM-C-04",
        "TM-C-05",
        "TM-C-06",
        "TM-C-07",
        "TM-C-08",
        "TM-C-09",
        "TM-C-10",
        "TM-C-11",
        "TM-C-12"
      ]
    },
    {
      "id": "D",
      "troncalId": "D",
      "label": "Troncal Calle 80 (D)",
      "color": "#6F2282",
      "path": "M 280 750 L 280 610 L 415 470 L 460 355 L 500 310 L 530 190",
      "stationIds": [
        "TM-D-01",
        "TM-D-02",
        "TM-D-03",
        "TM-D-04",
        "TM-D-05",
        "TM-D-06",
        "TM-D-07",
        "TM-D-08",
        "TM-D-09",
        "TM-D-10",
        "TM-D-11"
      ]
    },
    {
      "id": "E",
      "troncalId": "E",
      "label": "Troncal NQS Central (E)",
      "color": "#0FA3D8",
      "path": "M 530 440 L 930 440 L 985 340 L 1080 340 L 1080 440 L 1235 520",
      "stationIds": [
        "TM-G-10",
        "TM-E-07",
        "TM-E-04",
        "TM-E-05",
        "TM-E-06",
        "TM-G-09",
        "TM-G-08",
        "TM-E-08",
        "TM-E-09",
        "TM-E-10"
      ]
    },
    {
      "id": "K",
      "troncalId": "K",
      "label": "Troncal Calle 26 (K)",
      "color": "#F37021",
      "path": "M 730 890 L 730 580 L 870 375 L 870 190",
      "stationIds": [
        "TM-K-01",
        "TM-K-02",
        "TM-K-03",
        "TM-K-04",
        "TM-K-05",
        "TM-K-06",
        "TM-K-07",
        "TM-K-08",
        "TM-K-09",
        "TM-K-10",
        "TM-K-11"
      ]
    },
    {
      "id": "F",
      "troncalId": "F",
      "label": "Troncal Américas (F)",
      "color": "#C8102E",
      "path": "M 1170 810 L 1060 810 L 1075 740 L 1060 670 L 965 470 L 965 370 L 985 340",
      "stationIds": [
        "TM-F-01",
        "TM-F-12",
        "TM-F-13",
        "TM-F-14",
        "TM-F-15",
        "TM-F-02",
        "TM-F-03",
        "TM-F-04",
        "TM-F-05",
        "TM-F-06",
        "TM-F-07",
        "TM-F-08",
        "TM-F-09",
        "TM-F-10",
        "TM-F-11"
      ]
    },
    {
      "id": "G",
      "troncalId": "G",
      "label": "Troncal NQS Sur (G)",
      "color": "#0FA3D8",
      "path": "M 1080 440 L 1210 520 L 1210 785 L 1380 930",
      "stationIds": [
        "TM-G-07",
        "TM-G-06",
        "TM-G-05",
        "TM-G-02",
        "TM-G-04",
        "TM-G-03",
        "TM-G-15",
        "TM-G-13",
        "TM-G-14",
        "TM-G-01",
        "TM-G-11",
        "TM-G-12"
      ]
    },
    {
      "id": "H",
      "troncalId": "H",
      "label": "Troncal Caracas Sur (H)",
      "color": "#E8001D",
      "path": "M 1030 190 L 1050 260 L 1150 260 L 1320 410 L 1400 490 L 1565 490",
      "stationIds": [
        "TM-H-06",
        "TM-H-05",
        "TM-H-07",
        "TM-H-08",
        "TM-H-04",
        "TM-H-09",
        "TM-H-10",
        "TM-H-11",
        "TM-H-03",
        "TM-H-12",
        "TM-H-15",
        "TM-H-16",
        "TM-H-01"
      ]
    },
    {
      "id": "H_TUNAL",
      "troncalId": "H",
      "label": "Caracas Sur - Ramal Tunal (H)",
      "color": "#E8001D",
      "path": "M 1360 455 L 1360 605",
      "stationIds": [
        "TM-H-13",
        "TM-H-14",
        "TM-H-02"
      ]
    },
    {
      "id": "J",
      "troncalId": "J",
      "label": "Eje Ambiental (J)",
      "color": "#00B5E2",
      "path": "M 985 190 L 985 60",
      "stationIds": [
        "TM-J-01",
        "TM-J-02"
      ]
    },
    {
      "id": "L",
      "troncalId": "L",
      "label": "Troncal Carrera 10 (L)",
      "color": "#8A9EA7",
      "path": "M 870 140 L 1450 140",
      "stationIds": [
        "TM-L-02",
        "TM-L-04",
        "TM-L-03",
        "TM-L-05",
        "TM-L-06",
        "TM-L-07",
        "TM-L-08",
        "TM-L-09",
        "TM-L-01"
      ]
    }
  ],
  "connections": [
    {
      "id": "transbordo-jimenez",
      "label": "Transbordo Av. Jiménez - Eje Ambiental",
      "stationIds": [
        "TM-A-12",
        "TM-J-01"
      ],
      "path": "M 985 190 L 985 140"
    },
    {
      "id": "transbordo-san-diego",
      "label": "Conexión Centro Memoria - San Diego",
      "stationIds": [
        "TM-K-11",
        "TM-L-02"
      ],
      "path": "M 870 375 L 870 140"
    },
    {
      "id": "transbordo-ricaurte",
      "label": "Transbordo Ricaurte (Américas / NQS)",
      "stationIds": [
        "TM-F-11",
        "TM-E-08"
      ],
      "path": "M 985 340 L 1080 340"
    },
    {
      "id": "transbordo-heroes",
      "label": "Héroes / Autonorte / Caracas",
      "stationIds": [
        "TM-B-15",
        "TM-A-01"
      ],
      "path": "M 530 190 L 570 190"
    },
    {
      "id": "transbordo-militar",
      "label": "Escuela Militar / NQS / Calle 80",
      "stationIds": [
        "TM-D-10",
        "TM-C-12"
      ],
      "path": "M 435 400 L 415 355"
    }
  ]
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = TRANSMILENIO_LAYOUT;
}
