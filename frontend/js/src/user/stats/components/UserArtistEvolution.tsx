import { ResponsiveStream } from "@nivo/stream";
import * as React from "react";
import { faExclamationCircle, faLink } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { IconProp } from "@fortawesome/fontawesome-svg-core";
import { useQuery } from "@tanstack/react-query";
import Card from "../../../components/Card";
import Loader from "../../../components/Loader";
import { COLOR_BLACK } from "../../../utils/constants";
import GlobalAppContext from "../../../utils/GlobalAppContext";

export type UserArtistEvolutionProps = {
  range: UserStatsAPIRange;
  user?: ListenBrainzUser;
};

export declare type ChartDataItem = {
  label: string;
  [albumName: string]: number | string;
};

export default function UserArtistEvolution(props: UserArtistEvolutionProps) {
  const { APIService } = React.useContext(GlobalAppContext);

  // Props
  const { user, range } = props;

  const { data: loaderData, isLoading: loading } = useQuery({
    queryKey: ["userArtistEvolution", user?.name, range],
    queryFn: async () => {
      try {
        const queryData = await APIService.getUserArtistEvolution(
          user?.name,
          range
        );
        return { data: queryData, hasError: false, errorMessage: "" };
      } catch (error) {
        return {
          data: { result: [] } as UserArtistEvolutionResponse,
          hasError: true,
          errorMessage: error.message,
        };
      }
    },
  });

  const {
    data: rawData = { result: [] } as UserArtistEvolutionResponse,
    hasError = false,
    errorMessage = "",
  } = loaderData || {};

  const processData = (data?: UserArtistEvolutionResponse) => {
    if (!data || !data.result || data.result.length === 0) {
      return [];
    }
    // Process the data according to the API response structure
    // This would need to be adjusted based on the actual API response format
    return data.result.map((day) => ({
      label: day.date,
      ...day.artists.reduce(
        (acc, artist) => ({ ...acc, [artist.name]: artist.listen_count }),
        {} as Record<string, number>
      ),
    })) as ChartDataItem[];
  };

  const [chartData, setChartData] = React.useState<ChartDataItem[]>([]);

  React.useEffect(() => {
    if (rawData && rawData.result.length > 0) {
      const processedData = processData(rawData);
      setChartData(processedData);
    }
  }, [rawData]);

  // Get album keys for the stream chart
  const albumKeys = React.useMemo(() => {
    if (chartData.length === 0) return [];
    return Array.from(
      new Set(
        chartData.flatMap((item) =>
          Object.keys(item).filter((key) => key !== "label")
        )
      )
    );
  }, [chartData]);

  // Prepare data for ResponsiveStream
  const streamData = chartData;

  return (
    <Card className="user-stats-card" data-testid="user-artist-evolution">
      <div className="row">
        <div className="col-xs-10">
          <h3 className="capitalize-bold" style={{ marginLeft: 20 }}>
            Artist Evolution
          </h3>
        </div>
        <div className="col-xs-2 text-right">
          <h4 style={{ marginTop: 20 }}>
            <a href="#artist-evolution">
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
                <ResponsiveStream
                  data={streamData}
                  keys={albumKeys}
                  margin={{ top: 20, right: 100, bottom: 60, left: 60 }}
                  axisTop={null}
                  axisRight={null}
                  axisBottom={{
                    tickSize: 5,
                    tickPadding: 5,
                    tickRotation: 0,
                    legendOffset: 36,
                    truncateTickAt: 0,
                    format: (index) => {
                      // Convert the numeric index to the corresponding day label
                      return chartData[index]?.label || "";
                    },
                  }}
                  axisLeft={{
                    tickSize: 5,
                    tickPadding: 5,
                    tickRotation: 0,
                    legendOffset: -40,
                    truncateTickAt: 0,
                  }}
                  enableGridX
                  enableGridY={false}
                  offsetType="silhouette"
                  colors={{ scheme: "nivo" }}
                  fillOpacity={0.85}
                  borderColor={{ theme: "background" }}
                  dotSize={8}
                  dotColor={{ from: "color" }}
                  dotBorderWidth={2}
                  dotBorderColor={{
                    from: "color",
                    modifiers: [["darker", 0.7]],
                  }}
                  legends={[
                    {
                      anchor: "bottom-right",
                      direction: "column",
                      translateX: 100,
                      itemWidth: 80,
                      itemHeight: 20,
                      itemTextColor: "#999999",
                      symbolSize: 12,
                      symbolShape: "circle",
                      effects: [
                        {
                          on: "hover",
                          style: {
                            itemTextColor: "#000000",
                          },
                        },
                      ],
                    },
                  ]}
                />
              </div>
            </div>
          </div>
        )}
      </Loader>
    </Card>
  );
}
