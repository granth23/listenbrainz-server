import { ResponsiveBar } from "@nivo/bar";
import * as React from "react";
import { faExclamationCircle, faLink } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { IconProp } from "@fortawesome/fontawesome-svg-core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Card from "../../../components/Card";
import Loader from "../../../components/Loader";
import { COLOR_BLACK } from "../../../utils/constants";
import GlobalAppContext from "../../../utils/GlobalAppContext";

export type UserArtistActivityProps = {
  range: UserStatsAPIRange;
  user?: ListenBrainzUser;
};

export declare type ChartDataItem = {
  label: string;
  artistName: string; // Store the original artist name
  [albumName: string]: number | string;
};

export default function UserArtistActivity(props: UserArtistActivityProps) {
  const { APIService } = React.useContext(GlobalAppContext);
  const navigate = useNavigate();

  // Props
  const { user, range } = props;

  const { data: loaderData, isLoading: loading } = useQuery({
    queryKey: ["userArtistActivity", user?.name, range],
    queryFn: async () => {
      try {
        const queryData = await APIService.getUserArtistActivity(
          user?.name,
          range
        );
        return { data: queryData, hasError: false, errorMessage: "" };
      } catch (error) {
        return {
          data: { result: [] } as UserArtistActivityResponse,
          hasError: true,
          errorMessage: error.message,
        };
      }
    },
  });

  const {
    data: rawData = { result: [] } as UserArtistActivityResponse,
    hasError = false,
    errorMessage = "",
  } = loaderData || {};

  const processData = (data?: UserArtistActivityResponse) => {
    if (!data || !data.result || data.result.length === 0) {
      return [];
    }
    return data.result.map((artist) => {
      let wrappedLabel = artist.name.replace(/(.{14})/g, "$1-\n");
      if (wrappedLabel.endsWith("-\n")) {
        wrappedLabel = wrappedLabel.slice(0, -2); // Remove the last hyphen and keep the newline
      }
      return {
        label: wrappedLabel,
        artistName: artist.name, // Store the original artist name
        ...artist.albums.reduce(
          (acc, album) => ({ ...acc, [album.name]: album.listen_count }),
          {} as Record<string, number>
        ),
      };
    }) as ChartDataItem[];
  };
  const [chartData, setChartData] = React.useState<ChartDataItem[]>([]);

  const albumRedirectMapping = React.useMemo(() => {
    const mapping: Record<string, string> = {};
    if (rawData && rawData.result) {
      rawData.result.forEach((artist) => {
        artist.albums.forEach((album) => {
          if (album.release_group_mbid) {
            mapping[`${artist.name}-${album.name}`] = album.release_group_mbid;
          }
        });
      });
    }
    return mapping;
  }, [rawData]);

  React.useEffect(() => {
    if (rawData && rawData.result.length > 0) {
      const processedData = processData(rawData);
      setChartData(processedData);
    }
  }, [rawData]);

  // Custom tooltip component that only shows album name and count
  function CustomTooltip({
    id,
    value,
    color,
  }: {
    id: string;
    value: number;
    color: string;
  }) {
    return (
      <div
        style={{
          padding: "10px",
          background: "white",
          border: `1px solid ${color}`,
          borderRadius: "4px",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}
      >
        <strong>
          {id}: {value}
        </strong>
      </div>
    );
  }

  // Function to handle artist label click
  const handleArtistLabelClick = () => {
    window.open(
      `https://www.google.com/search?q=${encodeURIComponent("cnjddc")}`,
      "_blank"
    );
  };

  return (
    <Card className="user-stats-card" data-testid="user-artist-activity">
      <div className="row">
        <div className="col-xs-10">
          <h3 className="capitalize-bold" style={{ marginLeft: 20 }}>
            Artist Activity
          </h3>
        </div>
        <div className="col-xs-2 text-right">
          <h4 style={{ marginTop: 20 }}>
            <a href="#artist-activity">
              <FontAwesomeIcon
                icon={faLink as IconProp}
                size="sm"
                color={COLOR_BLACK}
                style={{ marginRight: 20 }}
              />
            </a>
          </h4>
        </div>
      </div>
      <Loader isLoading={loading}>
        {hasError ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "inherit",
            }}
          >
            <span style={{ fontSize: 24 }}>
              <FontAwesomeIcon icon={faExclamationCircle as IconProp} />{" "}
              {errorMessage}
            </span>
          </div>
        ) : (
          <div className="row">
            <div className="col-xs-12">
              <div
                style={{ width: "100%", height: "600px", minHeight: "400px" }}
              >
                <ResponsiveBar
                  data={chartData}
                  keys={Array.from(
                    new Set(
                      chartData.flatMap((item) =>
                        Object.keys(item).filter(
                          (key) => key !== "label" && key !== "artistName"
                        )
                      )
                    )
                  )}
                  indexBy="label"
                  margin={{ top: 20, right: 80, bottom: 80, left: 80 }}
                  padding={0.2}
                  layout="vertical"
                  colors={{ scheme: "nivo" }}
                  borderColor={{ from: "color", modifiers: [["darker", 1.6]] }}
                  enableLabel={false}
                  axisBottom={{
                    tickSize: 5,
                    tickPadding: 5,
                    tickRotation: -45,
                    renderTick: (tick) => {
                      return (
                        <g
                          transform={`translate(${tick.x},${tick.y})`}
                          onClick={() => handleArtistLabelClick()}
                          style={{ cursor: "pointer" }}
                        >
                          {tick.value
                            .split("\n")
                            .map((line: string, i: number) => (
                              <text
                                key={line}
                                x={0}
                                y={10 + i * 15}
                                textAnchor="end"
                                dominantBaseline="middle"
                                style={{
                                  fontSize: 10,
                                  fill: "#0000EE", // Use link color
                                  textDecoration: "underline",
                                  transform: `rotate(-45deg)`,
                                }}
                              >
                                {line}
                              </text>
                            ))}
                        </g>
                      );
                    },
                  }}
                  onClick={(barData, event) => {
                    const albumName = barData.id;
                    const artistName = barData.indexValue;
                    const releaseGroupMbid =
                      albumRedirectMapping[`${artistName}-${albumName}`];
                    if (releaseGroupMbid) {
                      navigate(`/album/${releaseGroupMbid}`);
                    }
                  }}
                  tooltip={({ id, value, color }) => (
                    <CustomTooltip
                      id={id as string}
                      value={value}
                      color={color}
                    />
                  )}
                />
              </div>
            </div>
          </div>
        )}
      </Loader>
    </Card>
  );
}
